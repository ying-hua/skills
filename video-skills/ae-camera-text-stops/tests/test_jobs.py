import json
from pathlib import Path
import sys
import tempfile
import unittest

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
from make_job import create_job, plan, validate


class JobTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((SKILL / "assets" / "job.example.json").read_text(encoding="utf-8"))
        self.directory = Path(tempfile.gettempdir()) / "ae-job-test-base"

    def valid(self):
        return validate(self.config, self.directory)

    def test_example_and_geometry(self):
        job = self.valid()
        for output in job["outputs"]:
            keys = plan(job, output)
            self.assertEqual([k["frame"] for k in keys], [0, 49, 53, 71, 75, 148])
            for index, shot in enumerate(job["shots"]):
                self.assertEqual(keys[index * 2]["position"], keys[index * 2 + 1]["position"])
                self.assertEqual(keys[index * 2]["target"], keys[index * 2 + 1]["target"])
                expected_x = output["width"] / 2 + shot["target"][0] - job["sourceWidth"] / 2
                self.assertEqual(keys[index * 2]["target"][0], expected_x)
                self.assertGreater(keys[index * 2]["position"][1], keys[index * 2]["target"][1])

    def test_default_is_landscape_only(self):
        outputs = self.valid()["outputs"]
        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0]["name"], "Landscape")
        self.assertGreater(outputs[0]["width"], outputs[0]["height"])

    def test_reject_overlap(self):
        self.config["shots"][1]["startFrame"] = 49
        with self.assertRaises(ValueError):
            self.valid()

    def test_reject_missing_tail(self):
        self.config["shots"][-1]["endFrame"] = 147
        with self.assertRaises(ValueError):
            self.valid()

    def test_reject_nonfinite(self):
        self.config["shots"][1]["target"][0] = float("nan")
        with self.assertRaises(ValueError):
            self.valid()

    def test_reject_target_outside_video(self):
        self.config["shots"][0]["target"] = [-1, 50]
        with self.assertRaises(ValueError):
            self.valid()

    def test_reject_media_overwrite(self):
        self.config["outputs"][0]["file"] = self.config["media"]
        with self.assertRaises(ValueError):
            self.valid()

    def test_reject_duplicate_output(self):
        duplicate = dict(self.config["outputs"][0], name="Landscape copy")
        self.config["outputs"].append(duplicate)
        with self.assertRaises(ValueError):
            self.valid()

    def test_reject_odd_h264_dimensions(self):
        self.config["outputs"][0]["width"] = 1475
        with self.assertRaises(ValueError):
            self.valid()

    def test_reject_camera_behind_plane(self):
        self.config["shots"][0]["cameraOffset"][2] = 100
        with self.assertRaises(ValueError):
            self.valid()

    def test_reject_boolean_number(self):
        self.config["fps"] = True
        with self.assertRaises(ValueError):
            self.valid()

    def test_creation_and_overwrite_guards(self):
        with tempfile.TemporaryDirectory(prefix="ae-skill-job-") as name:
            root = Path(name)
            self.config["media"] = "source.mp4"
            (root / "source.mp4").write_bytes(b"placeholder; no AE or media decoding in configuration tests")
            config_path = root / "job.json"
            config_path.write_text(json.dumps(self.config), encoding="utf-8")
            launcher = create_job(config_path, root / "work")
            self.assertTrue(launcher.is_file())
            resolved = json.loads((root / "work" / "job.resolved.json").read_text(encoding="utf-8"))
            self.assertEqual(len(resolved["outputs"][0]["keys"]), 6)
            self.assertIn("AE_CAMERA_CONFIG", launcher.read_text(encoding="utf-8"))
            with self.assertRaises(ValueError):
                create_job(config_path, root / "work")
            Path(resolved["project"]).write_bytes(b"existing project")
            with self.assertRaises(ValueError):
                create_job(config_path, root / "another-work")
            self.assertEqual(Path(resolved["project"]).read_bytes(), b"existing project")


if __name__ == "__main__":
    unittest.main()
