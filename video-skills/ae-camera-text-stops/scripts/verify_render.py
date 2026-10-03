"""Check rendered reading holds. Cursor continuity needs a separate source-motion check."""
import argparse
import json
import subprocess
from fractions import Fraction
from pathlib import Path

import cv2
import numpy as np

from make_job import validate


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def probe(path):
    return json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,width,height,r_frame_rate,nb_frames", "-of", "json", str(path),
    ]))


def frame_at(path, index):
    capture = cv2.VideoCapture(str(path))
    capture.set(cv2.CAP_PROP_POS_FRAMES, index)
    ok, image = capture.read()
    capture.release()
    check(ok, f"Cannot read {path} frame {index}")
    return image


def recover(source, rendered):
    sift = cv2.SIFT_create(nfeatures=6000)
    src_points, src_desc = sift.detectAndCompute(cv2.cvtColor(source, cv2.COLOR_BGR2GRAY), None)
    dst_points, dst_desc = sift.detectAndCompute(cv2.cvtColor(rendered, cv2.COLOR_BGR2GRAY), None)
    check(src_desc is not None and dst_desc is not None, "Insufficient texture for feature verification")
    pairs = cv2.BFMatcher().knnMatch(src_desc, dst_desc, k=2)
    good = [pair[0] for pair in pairs if len(pair) == 2 and pair[0].distance < 0.7 * pair[1].distance]
    check(len(good) >= 12, "Insufficient source/render feature matches")
    src = np.float32([src_points[m.queryIdx].pt for m in good])
    dst = np.float32([dst_points[m.trainIdx].pt for m in good])
    matrix, inliers = cv2.findHomography(src, dst, cv2.RANSAC, 3)
    check(matrix is not None and int(inliers.sum()) >= 10, "Cannot recover video plane geometry")
    height, width = source.shape[:2]
    corners = cv2.perspectiveTransform(np.float32([[[0, 0], [width, 0], [width, height], [0, height]]]), matrix)[0]
    check(np.isfinite(corners).all(), "Invalid projected video corners")
    return matrix, corners


def verify(job):
    source_info = probe(job["media"])
    source_video = next(s for s in source_info["streams"] if s["codec_type"] == "video")
    check((source_video["width"], source_video["height"]) == (job["sourceWidth"], job["sourceHeight"]), "Source dimensions mismatch")
    check(abs(float(Fraction(source_video["r_frame_rate"])) - job["fps"]) < 0.001, "Source frame rate mismatch")
    check(int(source_video["nb_frames"]) == job["frameCount"], "Prepared source frame count mismatch")
    needs_audio = any(s["codec_type"] == "audio" for s in source_info["streams"])
    results = []
    for output in job["outputs"]:
        path = Path(output["file"])
        info = probe(path)
        video = next(s for s in info["streams"] if s["codec_type"] == "video")
        check((video["width"], video["height"]) == (output["width"], output["height"]), "Rendered dimensions mismatch")
        check(abs(float(Fraction(video["r_frame_rate"])) - job["fps"]) < 0.001, "Rendered fps mismatch")
        check(abs(float(info["format"]["duration"]) - job["frameCount"] / job["fps"]) < 0.5 / job["fps"], "Rendered duration mismatch")
        check(not needs_audio or any(s["codec_type"] == "audio" for s in info["streams"]), "Audio missing from render")
        subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"], check=True, stdout=subprocess.DEVNULL)
        capture = cv2.VideoCapture(str(path))
        fractions = []
        while True:
            ok, image = capture.read()
            if not ok:
                break
            fractions.append(float((image.max(axis=2) > 30).mean()))
        capture.release()
        check(len(fractions) == job["frameCount"], "Not all video frames decoded")
        check(min(fractions) > 0.1, "Black or almost empty frame; inspect the output")
        errors, drifts = [], []
        for shot in job["shots"]:
            start, end = shot["startFrame"], shot["endFrame"]
            samples = sorted({start + 1, (start + end) // 2, max(start, end - 1)})
            recovered = []
            for frame in samples:
                original = frame_at(job["media"], frame)
                rendered = frame_at(path, frame)
                matrix, corners = recover(original, rendered)
                target = cv2.perspectiveTransform(np.float32([[shot["target"]]]), matrix)[0, 0]
                error = float(np.linalg.norm(target - [output["width"] / 2, output["height"] / 2]))
                check(error < 1.0, f"{output['name']}: target is not centered during {shot['label']}: {error:.3f}px")
                errors.append(error)
                recovered.append(corners)
            drift = max(float(np.abs(corners - recovered[0]).max()) for corners in recovered)
            check(drift < 1.0, f"{output['name']}: camera drifts during {shot['label']}: {drift:.3f}px")
            drifts.append(drift)
        first = frame_at(path, 0)
        _, corners = recover(frame_at(job["media"], 0), first)
        outside = np.full(first.shape[:2], 255, np.uint8)
        cv2.fillConvexPoly(outside, np.rint(corners).astype(np.int32), 0)
        outside = cv2.erode(outside, np.ones((25, 25), np.uint8))
        background_samples = int(np.count_nonzero(outside))
        if background_samples:
            check(first[outside > 0].max() <= 2, "Exposed background is not black")
        results.append({
            "file": str(path), "frames": len(fractions), "max_target_error_px": max(errors),
            "hold_drift_px": drifts, "background_sample_pixels": background_samples,
            "cursor_continuity": "Not tested here; compare active source selection against the original.",
        })
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    job = validate(json.loads(args.job.read_text(encoding="utf-8-sig")), args.job.resolve().parent)
    result = json.dumps(verify(job), indent=2)
    print(result)
    if args.report:
        with args.report.open("x", encoding="utf-8") as file:
            file.write(result)


if __name__ == "__main__":
    main()
