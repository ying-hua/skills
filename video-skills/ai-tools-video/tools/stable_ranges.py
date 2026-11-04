"""找出录屏中画面静止(未滚动)的时间段。

用法: python tools/stable_ranges.py <video> [fps=10] [阈值=1.5] [最短秒数=0.6]
"""
import subprocess
import sys

import numpy as np

video = sys.argv[1]
fps = float(sys.argv[2]) if len(sys.argv) > 2 else 10
thr = float(sys.argv[3]) if len(sys.argv) > 3 else 1.5
min_len = float(sys.argv[4]) if len(sys.argv) > 4 else 0.6
W, H = 320, 180

raw = subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-vf", f"fps={fps},scale={W}:{H},format=gray",
                      "-f", "rawvideo", "-"], capture_output=True).stdout
frames = np.frombuffer(raw, np.uint8).reshape(-1, H, W).astype(np.float32)
diff = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))

ranges, start = [], None
for i, d in enumerate(diff):
    if d < thr:
        start = i if start is None else start
    else:
        if start is not None and (i - start) / fps >= min_len:
            ranges.append((start / fps, i / fps))
        start = None
if start is not None and (len(diff) - start) / fps >= min_len:
    ranges.append((start / fps, len(diff) / fps))
for a, b in ranges:
    print(f"{a:6.1f} - {b:6.1f}  ({b - a:.1f}s)")
