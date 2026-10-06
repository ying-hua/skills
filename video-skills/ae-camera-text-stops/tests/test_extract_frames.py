import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import cv2
import numpy as np

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
from extract_frames import extract, job_samples, uniform_indices
from make_job import validate


class SamplingTests(unittest.TestCase):
    def test_uniform_includes_ends_and_deduplicates_short_clips(self):
        self.assertEqual(uniform_indices(107, 3), [0, 53, 106])
        self.assertEqual(uniform_indices(2, 12), [0, 1])
        self.assertEqual(uniform_indices(1, 12), [0])
        with self.assertRaises(ValueError):
            uniform_indices(10, 0)

    def test_job_samples_stable_holds_and_all_short_move_frames(self):
        config = json.loads((SKILL / "assets" / "job.example.json").read_text(encoding="utf-8"))
        samples = job_samples(validate(config, SKILL / "assets"))
        self.assertEqual(list(samples), sorted(set(samples)))
        self.assertIn(0, samples)
        self.assertIn(148, samples)
        for start, end in [(0, 49), (53, 71), (75, 148)]:
            for frame in (start + 1, (start + end) // 2, end - 1):
                self.assertIn(frame, samples)
        for frame in list(range(49, 54)) + list(range(71, 76)):
            self.assertIn(frame, samples)

    def test_long_moves_are_bounded_and_two_frame_holds_are_valid(self):
        samples = job_samples({"frameCount": 104, "shots": [
            {"startFrame": 0, "endFrame": 1}, {"startFrame": 102, "endFrame": 103},
        ]})
        self.assertEqual(sum("move 1" in labels for labels in samples.values()), 9)
        self.assertTrue(all(0 <= frame < 104 for frame in samples))


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe required")
class ExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="ae-frame-review-")
        cls.root = Path(cls.temp.name)
        cls.video = cls.root / "sample with spaces.mp4"
        subprocess.run([
            "ffmpeg", "-v", "error", "-n", "-f", "lavfi", "-i",
            "testsrc2=size=160x90:rate=30:duration=1", "-an",
            "-c:v", "libx264", "-threads", "1", "-pix_fmt", "yuv420p", str(cls.video),
        ], check=True)
        cls.original_hash = hashlib.sha256(cls.video.read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def assert_source_unchanged(self):
        self.assertEqual(hashlib.sha256(self.video.read_bytes()).hexdigest(), self.original_hash)

    def test_exact_frames_dimensions_timestamps_and_pagination(self):
        directory = self.root / "paginated"
        report = extract(self.video, directory, frames=list(range(14)))
        self.assertEqual(report["decoded_frames"], 30)
        self.assertEqual(report["sample_count"], 14)
        self.assertEqual(report["contact_sheets"], ["contact_sheet_01.jpg", "contact_sheet_02.jpg"])
        self.assertEqual(len(list(directory.glob("frame_*.png"))), 14)
        capture = cv2.VideoCapture(str(self.video))
        try:
            for index, record in enumerate(report["frames"]):
                ok, expected = capture.read()
                self.assertTrue(ok)
                actual = cv2.imdecode(np.frombuffer((directory / record["file"]).read_bytes(), np.uint8), cv2.IMREAD_COLOR)
                self.assertTrue(np.array_equal(actual, expected))
                self.assertEqual(actual.shape, (90, 160, 3))
                self.assertAlmostEqual(record["seconds"], index / 30, places=5)
        finally:
            capture.release()
        sheet = cv2.imread(str(directory / report["contact_sheets"][0]))
        self.assertEqual(sheet.shape[:2], ((360 + 48) * 4, 640 * 3))
        self.assertEqual(json.loads((directory / "frames.json").read_text())["sample_count"], 14)
        self.assert_source_unchanged()

    def test_input_and_output_guards(self):
        with self.assertRaises(FileNotFoundError):
            extract(self.root / "missing.mp4", self.root / "missing-review")
        with self.assertRaises(FileExistsError):
            extract(self.video, self.video)
        directory = self.root / "existing"
        directory.mkdir()
        sentinel = directory / "keep.txt"
        sentinel.write_text("preserve")
        with self.assertRaises(FileExistsError):
            extract(self.video, directory)
        self.assertEqual(sentinel.read_text(), "preserve")
        for indices in ([-1], [30], []):
            with self.assertRaises(ValueError):
                extract(self.video, self.root / "invalid", frames=indices)
        self.assertFalse((self.root / "invalid").exists())
        self.assert_source_unchanged()

    def test_job_output_validation_and_reading_samples(self):
        config = json.loads((SKILL / "assets" / "job.example.json").read_text())
        config["frameCount"] = 30
        config["outputs"][0].update(width=160, height=90, file=str(self.video))
        for shot, times in zip(config["shots"], [(0, 7), (11, 17), (21, 29)]):
            shot.update(startFrame=times[0], endFrame=times[1])
        job_path = self.root / "job.json"
        job_path.write_text(json.dumps(config))
        report = extract(self.video, self.root / "job-review", job_path=job_path)
        self.assertEqual(report["frames"][0]["frame"], 0)
        self.assertEqual(report["frames"][-1]["frame"], 29)
        self.assertTrue(any("move 1" in frame["labels"] for frame in report["frames"]))
        config["frameCount"] = 31
        config["shots"][-1]["endFrame"] = 30
        job_path.write_text(json.dumps(config))
        with self.assertRaisesRegex(ValueError, "frame count"):
            extract(self.video, self.root / "wrong-job", job_path=job_path)
        self.assertFalse((self.root / "wrong-job").exists())
        self.assert_source_unchanged()


if __name__ == "__main__":
    unittest.main()
