"""粗略预览：按 Timeline 记录的信息合成指定时刻的画面(不含剪映的入场/出场动画)，用来检查构图。"""
import io
import os
import subprocess

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont

import config
from jy import CW, CH

TEXT_PX_PER_SIZE = 6.0  # 用片头2预设校准：剪映字号 1 ≈ 6 像素(1080 宽画布，抖音美好体)
_frame_cache = {}


def _video_frame(path, t):
    key = (path, round(t, 2))
    if key not in _frame_cache:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0, t):.3f}", "-i", path, "-frames:v", "1",
                              "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True).stdout
        _frame_cache[key] = Image.open(io.BytesIO(raw)).convert("RGBA") if raw else None
    return _frame_cache[key]


def _interp(kf, idx, t, base):
    pts = [(f[0], f[idx]) for f in kf if f[idx] is not None]
    if not pts:
        return base
    pts.sort()
    if t <= pts[0][0]:
        return pts[0][1]
    for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
        if t0 <= t <= t1:
            return v0 + (v1 - v0) * (t - t0) / max(1e-9, t1 - t0)
    return pts[-1][1]


def render(tl, t, bg_path=None, scale=0.5):
    canvas = Image.new("RGBA", (CW, CH), (0, 0, 0, 255))
    if bg_path:
        f = _video_frame(bg_path, t)
        if f:
            canvas.alpha_composite(f.resize((CW, CH)))
    for layer, _ in tl.layers:
        for start, end, seg in sorted(tl.items[layer], key=lambda x: x[0]):
            if not (start <= t < end):
                continue
            m = tl.meta.get(id(seg))
            if m is None:
                continue
            rel = t - start
            if m["type"] == "img":
                p = m["path"]
                if p.lower().endswith((".mp4", ".mov")):
                    img = _video_frame(p, (m["src_start"] or 0) + rel * m["speed"])
                else:
                    img = Image.open(p).convert("RGBA")
                if img is None:
                    continue
                k = _interp(m["kf"], 1, rel, m["k"])
                cx = _interp(m["kf"], 2, rel, m["cx"])
                cy = _interp(m["kf"], 3, rel, m["cy"])
                a = _interp(m["kf"], 4, rel, m["alpha"])
                w, h = max(1, int(img.width * k)), max(1, int(img.height * k))
                im = img.resize((w, h), Image.BILINEAR)
                if m.get("rot"):
                    im = im.rotate(-m["rot"], expand=True, resample=Image.BILINEAR)
                pos = (int(cx - im.width / 2), int(cy - im.height / 2))
                if m.get("blend") == "screen":
                    layer_img = Image.new("RGB", (CW, CH), (0, 0, 0))
                    layer_img.paste(im.convert("RGB"), pos)
                    canvas = ImageChops.screen(canvas.convert("RGB"), layer_img).convert("RGBA")
                else:
                    if a < 1.0:
                        al = im.split()[3].point(lambda v: int(v * a))
                        im.putalpha(al)
                    tmp = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
                    tmp.paste(im, pos, im)
                    canvas.alpha_composite(tmp)
            elif m["type"] == "text":
                px = int(m["size"] * TEXT_PX_PER_SIZE)
                font = ImageFont.truetype(os.path.join(config.get("FONT_DIR"), "msyhbd.ttc"), px)
                d = ImageDraw.Draw(canvas)
                text = m["text"]
                cx = CW / 2 + m["x"] * CW / 2
                cy = CH / 2 - m["y"] * CH / 2
                tw = d.textlength(text, font=font)
                x = cx - tw / 2
                col = tuple(int(c * 255) for c in m["color"])
                hl = tuple(int(c * 255) for c in m["hl_color"])
                flags = [False] * len(text)
                for hword in m["highlights"]:
                    i = text.find(hword)
                    while i >= 0:
                        for j in range(i, i + len(hword)):
                            flags[j] = True
                        i = text.find(hword, i + len(hword))
                for ch, fl in zip(text, flags):
                    d.text((x, cy), ch, font=font, fill=hl if fl else col, anchor="lm",
                           stroke_width=max(2, px // 12) if m["border"] else 0, stroke_fill=(0, 0, 0))
                    x += d.textlength(ch, font=font)
    out = canvas.convert("RGB")
    return out.resize((int(CW * scale), int(CH * scale)))


def sheet(tl, times, out, bg_path=None, cols=6, scale=0.25):
    frames = [render(tl, t, bg_path, scale) for t in times]
    w, h = frames[0].size
    rows = (len(frames) + cols - 1) // cols
    img = Image.new("RGB", (cols * w + (cols - 1) * 6, rows * (h + 26)), (90, 0, 0))
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(os.path.join(config.get("FONT_DIR"), "msyh.ttc"), 18)
    for i, (t, fr) in enumerate(zip(times, frames)):
        x, y = (i % cols) * (w + 6), (i // cols) * (h + 26)
        img.paste(fr, (x, y + 26))
        d.text((x + 4, y + 2), f"{t:.2f}s", font=f, fill=(255, 255, 0))
    img.save(out)
    return out
