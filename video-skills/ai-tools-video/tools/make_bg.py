"""渲染黑底 + 斜向飘动的「AI小成」文字背景 (1080x1920, 30fps)。

用法: python tools/make_bg.py <out.mp4> [秒数]
"""
import subprocess
import config
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

out = sys.argv[1]
seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 60
W, H, FPS = 1080, 1920, 30
ANGLE = 12          # 文字行逆时针倾斜角度
TEXT = "AI小成"
COLOR = (46, 46, 46)
FONT = ImageFont.truetype(os.path.join(config.get("FONT_DIR"), "msyhbd.ttc"), 74)
ROW_H = 132
SPEED = 26          # 像素/秒，相邻行反向

# 单行图案：文字重复，横向可无缝循环
gap = 44
tw = int(FONT.getlength(TEXT)) + gap
tile = Image.new("L", (tw, ROW_H), 0)
ImageDraw.Draw(tile).text((0, ROW_H // 2), TEXT, font=FONT, fill=255, anchor="lm")
# 斜体：水平错切
tile = tile.transform(tile.size, Image.AFFINE, (1, 0.18, -0.18 * ROW_H / 2, 0, 1, 0), Image.BICUBIC)
tile = np.array(tile)

S = 2600  # 旋转前的大画布边长
reps = S // tw + 2
row = np.tile(tile, (1, reps))
n_rows = S // ROW_H + 1

proc = subprocess.Popen([
    "ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
    "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", out,
], stdin=subprocess.PIPE)

color = np.array(COLOR, dtype=np.float32) / 255.0
for f in range(int(seconds * FPS)):
    t = f / FPS
    big = np.zeros((n_rows * ROW_H, S), dtype=np.uint8)
    for r in range(n_rows):
        d = int(t * SPEED * (1 if r % 2 else -1) + r * tw * 0.37) % tw
        big[r * ROW_H:(r + 1) * ROW_H] = row[:, d:d + S]
    img = Image.fromarray(big).rotate(ANGLE, resample=Image.BILINEAR)
    cx, cy = img.width // 2, img.height // 2
    crop = np.asarray(img.crop((cx - W // 2, cy - H // 2, cx + W // 2, cy + H // 2)), dtype=np.float32) / 255.0
    frame = (crop[..., None] * color * 255).astype(np.uint8)
    proc.stdin.write(frame.tobytes())
proc.stdin.close()
proc.wait()
print("done", out)
