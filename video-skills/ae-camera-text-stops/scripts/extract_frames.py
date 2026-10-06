"""Extract local MP4 review frames and paginated contact sheets; never launch an editor."""
import argparse
import json
import math
from pathlib import Path
import subprocess

import cv2
import numpy as np

from make_job import validate


def uniform_indices(frame_count, count):
    if frame_count < 1 or count < 1:
        raise ValueError("Frame count and sample count must be positive")
    count = min(frame_count, count)
    if count == 1:
        return [0]
    return [round(i * (frame_count - 1) / (count - 1)) for i in range(count)]


def job_samples(job):
    samples = {}

    def add(frame, label):
        samples.setdefault(frame, []).append(label)

    add(0, "first")
    add(job["frameCount"] - 1, "last")
    for index, shot in enumerate(job["shots"]):
        start, end = shot["startFrame"], shot["endFrame"]
        for frame in sorted({start + 1, (start + end) // 2, max(start, end - 1)}):
            add(frame, f"hold {index + 1}")
        if index + 1 < len(job["shots"]):
            next_start = job["shots"][index + 1]["startFrame"]
            # Four-frame moves are shown in full; long gaps stay bounded.
            for offset in uniform_indices(next_start - end + 1, 9):
                add(end + offset, f"move {index + 1}")
    return dict(sorted(samples.items()))


def probe_video(video):
    command = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,nb_frames,nb_read_frames",
        "-of", "json", str(video),
    ]

    def run(args):
        result = subprocess.run(args, capture_output=True, text=True, check=True)
        if result.stderr.strip():
            raise RuntimeError(result.stderr.strip())
        streams = json.loads(result.stdout)["streams"]
        if not streams:
            raise ValueError(f"No video stream: {video}")
        return streams[0]

    stream = run(command)
    count = stream.get("nb_frames")
    if count in (None, "N/A"):
        stream = run(command[:1] + ["-count_frames"] + command[1:])
        count = stream.get("nb_read_frames")
    if count in (None, "N/A") or int(count) < 1:
        raise ValueError(f"Cannot determine decoded frame count: {video}")
    return int(count), int(stream["width"]), int(stream["height"])


def write_image(path, image):
    ok, encoded = cv2.imencode(path.suffix, image)
    if not ok:
        raise RuntimeError(f"Cannot encode image: {path}")
    with path.open("xb") as file:
        file.write(encoded.tobytes())


def save_sheet(directory, page, tiles):
    rows = math.ceil(len(tiles) / 3)
    height, width = tiles[0].shape[:2]
    sheet = np.zeros((height * rows, width * 3, 3), np.uint8)
    for index, tile in enumerate(tiles):
        y, x = (index // 3) * height, (index % 3) * width
        sheet[y:y + height, x:x + width] = tile
    name = f"contact_sheet_{page:02d}.jpg"
    write_image(directory / name, sheet)
    return name


def extract(video, out_dir, *, job_path=None, frames=None, count=12):
    video, out_dir = Path(video).resolve(), Path(out_dir).resolve()
    if not video.is_file():
        raise FileNotFoundError(video)
    if out_dir.exists():
        raise FileExistsError(f"Choose a new review directory; refusing overwrite: {out_dir}")
    frame_count, width, height = probe_video(video)
    job = None
    if job_path is not None:
        if frames is not None:
            raise ValueError("Choose either a job or explicit frame indices")
        job_path = Path(job_path).resolve()
        job = validate(json.loads(job_path.read_text(encoding="utf-8-sig")), job_path.parent)
        output = next((out for out in job["outputs"] if Path(out["file"]) == video), None)
        if output is None:
            raise ValueError("Video is not a rendered output of this job")
        if frame_count != job["frameCount"] or (width, height) != (output["width"], output["height"]):
            raise ValueError("Rendered frame count or dimensions differ from the job")
        samples = job_samples(job)
    elif frames is not None:
        if not frames or any(type(frame) is not int or not 0 <= frame < frame_count for frame in frames):
            raise ValueError(f"Frame indices must be in 0..{frame_count - 1} (zero based)")
        samples = {frame: ["manual"] for frame in sorted(set(frames))}
    else:
        samples = {frame: ["overview"] for frame in uniform_indices(frame_count, count)}

    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        capture.release()
        raise RuntimeError(f"Cannot open video: {video}")
    records, sheets, tiles = [], [], []
    thumbnail_height = max(1, round(height * 640 / width))
    try:
        out_dir.mkdir(parents=True, exist_ok=False)
        for index in range(frame_count):
            ok, image = capture.read()
            if not ok:
                raise RuntimeError(f"Decoding ended at frame {index}; expected {frame_count}")
            if image.shape[:2] != (height, width):
                raise RuntimeError(f"Frame dimensions changed at frame {index}")
            if index not in samples:
                continue
            seconds = float(capture.get(cv2.CAP_PROP_POS_MSEC)) / 1000
            if not math.isfinite(seconds) or seconds < 0 or (records and seconds <= records[-1]["seconds"]):
                raise RuntimeError(f"Invalid decoded timestamp at frame {index}")
            if job is not None and abs(seconds - index / job["fps"]) > 0.5 / job["fps"]:
                raise ValueError(f"Rendered timestamps differ from the job at frame {index}")
            filename = f"frame_{index:06d}.png"
            write_image(out_dir / filename, image)
            tile = cv2.copyMakeBorder(
                cv2.resize(image, (640, thumbnail_height), interpolation=cv2.INTER_AREA),
                48, 0, 0, 0, cv2.BORDER_CONSTANT,
            )
            label = " / ".join(samples[index])
            cv2.putText(tile, f"frame {index:06d} | {seconds:.3f}s", (10, 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1)
            cv2.putText(tile, label, (10, 38), cv2.FONT_HERSHEY_SIMPLEX,
                        0.45, (180, 220, 255), 1)
            records.append({"frame": index, "seconds": seconds, "labels": samples[index], "file": filename})
            tiles.append(tile)
            if len(tiles) == 12:
                sheets.append(save_sheet(out_dir, len(sheets) + 1, tiles))
                tiles = []
        if capture.read()[0]:
            raise RuntimeError("Decoded more frames than declared by the video")
        if tiles:
            sheets.append(save_sheet(out_dir, len(sheets) + 1, tiles))
    finally:
        capture.release()
    report = {
        "video": str(video), "job": str(job_path) if job_path else None,
        "width": width, "height": height, "decoded_frames": frame_count,
        "sample_count": len(records), "contact_sheets": sheets, "frames": records,
        "shots": job["shots"] if job else None,
        "review_status": "Extraction complete. Inspect the images; this does not certify camera holds or cursor continuity.",
    }
    with (out_dir / "frames.json").open("x", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path, help="Final rendered MP4, read only")
    parser.add_argument("--out-dir", type=Path, required=True, help="New directory for PNGs, sheets and manifest")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--job", type=Path, help="Sample reading holds and fast moves from this job")
    selection.add_argument("--frames", type=int, nargs="+", help="Explicit zero-based frame indices")
    selection.add_argument("--count", type=int, default=12, help="Uniform samples without a job (default: 12)")
    args = parser.parse_args()
    report = extract(args.video, args.out_dir, job_path=args.job, frames=args.frames, count=args.count)
    print(json.dumps({
        "review_directory": str(args.out_dir.resolve()), "sample_count": report["sample_count"],
        "contact_sheets": report["contact_sheets"], "review_status": report["review_status"],
    }, indent=2))


if __name__ == "__main__":
    main()
