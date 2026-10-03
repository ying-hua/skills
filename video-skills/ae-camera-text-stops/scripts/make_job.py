"""Validate a camera job and generate an AE launcher; never modify source media."""
import argparse
import copy
import json
import math
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value, label, positive=False):
    require(type(value) in (int, float) and math.isfinite(value), f"{label} must be finite")
    require(not positive or value > 0, f"{label} must be positive")
    return value


def integer(value, label, minimum=0):
    require(type(value) is int and value >= minimum, f"{label} must be an integer >= {minimum}")
    return value


def vector(value, length, label):
    require(isinstance(value, list) and len(value) == length, f"{label} requires {length} numbers")
    for item in value:
        number(item, label)


def resolve_file(value, directory, suffix, label):
    require(isinstance(value, str) and value.strip() and "\0" not in value, f"Invalid {label}")
    path = (directory / value).resolve()
    require(path.suffix.lower() == suffix, f"{label} must end with {suffix}")
    return str(path)


def validate(config, directory):
    job = copy.deepcopy(config)
    require(isinstance(job, dict), "Job must be an object")
    number(job.get("fps"), "fps", True)
    require(job["fps"] <= 120, "fps must be <=120")
    integer(job.get("frameCount"), "frameCount", 2)
    for key in ("sourceWidth", "sourceHeight"):
        integer(job.get(key), key, 2)
    number(job.get("sourceSpeed"), "sourceSpeed", True)
    job["media"] = resolve_file(job.get("media"), directory, ".mp4", "media")
    job["project"] = resolve_file(job.get("project"), directory, ".aep", "project")
    shots = job.get("shots")
    require(isinstance(shots, list) and len(shots) >= 2, "At least two shots are required")
    previous = None
    for index, shot in enumerate(shots):
        require(isinstance(shot, dict), "Each shot must be an object")
        require(isinstance(shot.get("label"), str) and shot["label"].strip(), "Shot label required")
        start = integer(shot.get("startFrame"), "startFrame")
        end = integer(shot.get("endFrame"), "endFrame")
        require(start < end < job["frameCount"], "Every hold must contain at least two frames")
        require(previous is None or start > previous, "Holds must be ordered, with a positive transition gap")
        require(index != 0 or start == 0, "First shot must begin at frame zero")
        previous = end
        vector(shot.get("target"), 2, "target")
        require(0 <= shot["target"][0] < job["sourceWidth"] and 0 <= shot["target"][1] < job["sourceHeight"], "Target is outside source")
        vector(shot.get("cameraOffset"), 3, "cameraOffset")
        require(shot["cameraOffset"][2] < 0, "Camera Z offset must be negative, in front of the video")
    require(shots[-1]["endFrame"] == job["frameCount"] - 1, "Last hold must reach the final frame")
    outputs = job.get("outputs")
    require(isinstance(outputs, list) and outputs, "At least one output is required")
    paths = {job["media"].casefold(), job["project"].casefold()}
    names = set()
    for out in outputs:
        require(isinstance(out, dict), "Output must be an object")
        require(isinstance(out.get("name"), str) and out["name"].strip(), "Output name required")
        require(out["name"] not in names, "Output names must be unique")
        names.add(out["name"])
        for key in ("width", "height"):
            integer(out.get(key), key, 2)
            require(out[key] % 2 == 0, "H.264 output dimensions must be even")
        number(out.get("zoom"), "zoom", True)
        out["file"] = resolve_file(out.get("file"), directory, ".mp4", "output")
        require(out["file"].casefold() not in paths, "Paths must be unique; outputs cannot replace media")
        paths.add(out["file"].casefold())
    return job


def plan(job, output):
    keys = []
    for shot in job["shots"]:
        target = [
            output["width"] / 2 + shot["target"][0] - job["sourceWidth"] / 2,
            output["height"] / 2 + shot["target"][1] - job["sourceHeight"] / 2,
            0,
        ]
        position = [target[a] + shot["cameraOffset"][a] for a in range(3)]
        for frame in (shot["startFrame"], shot["endFrame"]):
            keys.append({"frame": frame, "target": target[:], "position": position[:]})
    return keys


def create_job(config_path, work_dir):
    config_path = Path(config_path).resolve()
    job = validate(json.loads(config_path.read_text(encoding="utf-8-sig")), config_path.parent)
    require(Path(job["media"]).is_file(), f"Prepared media missing: {job['media']}")
    for path in [job["project"]] + [out["file"] for out in job["outputs"]]:
        require(not Path(path).exists(), f"Refusing overwrite: {path}")
    for out in job["outputs"]:
        out["keys"] = plan(job, out)
    work_dir = Path(work_dir).resolve()
    resolved = work_dir / "job.resolved.json"
    launcher = work_dir / "build.jsx"
    report = work_dir / "build-report.txt"
    protected = {job["media"].casefold(), job["project"].casefold()}
    protected.update(out["file"].casefold() for out in job["outputs"])
    for path in (resolved, launcher, report):
        require(str(path).casefold() not in protected and path != config_path, "Work files collide with job paths")
        require(not path.exists(), f"Work file already exists: {path}")
    work_dir.mkdir(parents=True, exist_ok=True)
    for path in [job["project"]] + [out["file"] for out in job["outputs"]]:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    job["report"] = str(report)
    builder = Path(__file__).with_name("build_camera.jsx")
    resolved.write_text(json.dumps(job, indent=2, ensure_ascii=True), encoding="utf-8")
    launcher.write_text(
        "#target aftereffects\nvar AE_CAMERA_CONFIG = " + json.dumps(job, ensure_ascii=True) + ";\n"
        "$.evalFile(new File(" + json.dumps(str(builder), ensure_ascii=True) + "));\n",
        encoding="utf-8",
    )
    return launcher


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        validate(json.loads(args.config.read_text(encoding="utf-8-sig")), args.config.resolve().parent)
        print("PASS: job schema, geometry, timeline, and path isolation")
    else:
        if args.out_dir is None:
            parser.error("--out-dir is required unless --validate-only is used")
        print(create_job(args.config, args.out_dir))


if __name__ == "__main__":
    main()
