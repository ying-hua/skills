"""本地渲染 MP4(不经过剪映)：把 jy.Timeline 里记录的画面层逐帧合成，再用 ffmpeg 混音。

和 preview.py 同一套坐标/关键帧逻辑，另外支持：
- 入场(放大弹出)/出场(缩小)动画的近似
- 视频素材顺序解码(不再每帧起一个 ffmpeg)
- 多进程分段渲染后拼接
剪映预设(片头2、文字弹出预设、1分钟背景)不在 Timeline 里，需要调用方用图片层自己画出来。
"""
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageChops, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fx  # noqa: E402
from jy import CW, CH  # noqa: E402

FPS = 30
TEXT_PX_PER_SIZE = 6.0


# ---------------------------------------------------------------- 场景：Timeline → 可 pickle 的列表

def scene_from(tl, bg_path=None):
    items = []
    for layer, _ in tl.layers:
        for start, end, seg in sorted(tl.items[layer], key=lambda x: x[0]):
            m = tl.meta.get(id(seg))
            if m is not None:
                items.append(dict(m, start=start, end=end))
    return dict(items=items, bg=bg_path)


# ---------------------------------------------------------------- 素材读取

class VideoReader:
    """按时间递增顺序读视频帧；时间回退或跳太远时从新位置重开。"""

    def __init__(self, path):
        self.path = path
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                              "stream=width,height", "-of", "csv=p=0", path], capture_output=True, text=True).stdout
        self.w, self.h = map(int, out.strip().split(",")[:2])
        self.proc, self.pos, self.cur = None, None, None

    def _open(self, t):
        if self.proc:
            self.proc.kill()
        self.proc = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{max(0, t):.3f}", "-i", self.path,
                                      "-vf", f"fps={FPS}", "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     bufsize=self.w * self.h * 4 * 2)
        self.pos, self.cur = max(0, t) - 1 / FPS, None

    def frame(self, t):
        if self.proc is None or t < self.pos - 1e-6 or t > self.pos + 1.0:
            self._open(t)
        while self.pos + 1 / FPS <= t + 1e-6 or self.cur is None:
            raw = self.proc.stdout.read(self.w * self.h * 4)
            if len(raw) < self.w * self.h * 4:
                break
            self.cur = Image.frombuffer("RGBA", (self.w, self.h), raw, "raw", "RGBA", 0, 1)
            self.pos += 1 / FPS
        return self.cur


class Assets:
    def __init__(self):
        self.imgs, self.videos, self.texts = {}, {}, {}

    def image(self, p):
        if p not in self.imgs:
            self.imgs[p] = Image.open(p).convert("RGBA")
        return self.imgs[p]

    def video(self, p, t):
        if p not in self.videos:
            self.videos[p] = VideoReader(p)
        return self.videos[p].frame(t)

    def text(self, m):
        key = (m["text"], m["size"], tuple(m["highlights"]))
        if key not in self.texts:
            self.texts[key] = _text_img(m)
        return self.texts[key]


def _text_img(m):
    px = int(m["size"] * TEXT_PX_PER_SIZE)
    font = fx.font_black(px)
    text = m["text"]
    flags = [False] * len(text)
    for h in m["highlights"]:
        i = text.find(h)
        while i >= 0:
            for j in range(i, i + len(h)):
                flags[j] = True
            i = text.find(h, i + len(h))
    sw = max(3, px // 9) if m["border"] else 0
    d0 = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    tw = int(d0.textlength(text, font=font)) + sw * 2 + 8
    img = Image.new("RGBA", (tw, int(px * 1.5) + sw * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    col = tuple(int(c * 255) for c in m["color"])
    hl = tuple(int(c * 255) for c in m["hl_color"])
    x = sw + 4
    for ch, fl in zip(text, flags):
        d.text((x, img.height / 2), ch, font=font, fill=hl if fl else col, anchor="lm",
               stroke_width=sw, stroke_fill=(0, 0, 0))
        x += d.textlength(ch, font=font)
    return img


# ---------------------------------------------------------------- 合成

def _interp(kf, idx, t, base):
    pts = sorted((f[0], f[idx]) for f in kf if f[idx] is not None)
    if not pts:
        return base
    if t <= pts[0][0]:
        return pts[0][1]
    for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
        if t0 <= t <= t1:
            return v0 + (v1 - v0) * (t - t0) / max(1e-9, t1 - t0)
    return pts[-1][1]


def _ease_out_back(p):
    c = 1.70158
    return 1 + (c + 1) * (p - 1) ** 3 + c * (p - 1) ** 2


def _anim(m, rel):
    """入场/出场动画的近似：返回 (缩放倍数, 透明度倍数)。"""
    s, a = 1.0, 1.0
    if m.get("intro") and rel < m["intro"]:
        p = rel / m["intro"]
        s, a = 0.3 + 0.7 * _ease_out_back(p), min(1.0, p * 2)
    rest = (m["end"] - m["start"]) - rel
    if m.get("outro") and rest < m["outro"]:
        p = max(0.0, rest / m["outro"])
        s, a = s * (0.6 + 0.4 * p), a * p
    return s, a


def _paste(canvas, im, x, y, screen=False):
    x, y = int(round(x)), int(round(y))
    l, t = max(0, x), max(0, y)
    r, b = min(CW, x + im.width), min(CH, y + im.height)
    if r <= l or b <= t:
        return canvas
    crop = im.crop((l - x, t - y, r - x, b - y))
    if screen:
        region = canvas.crop((l, t, r, b)).convert("RGB")
        canvas.paste(ImageChops.screen(region, crop.convert("RGB")).convert("RGBA"), (l, t))
    else:
        canvas.alpha_composite(crop, (l, t))
    return canvas


def render_frame(scene, A, t):
    canvas = Image.new("RGBA", (CW, CH), (0, 0, 0, 255))
    if scene["bg"]:
        f = A.video(scene["bg"], t)
        if f is not None:
            canvas.alpha_composite(f if f.size == (CW, CH) else f.resize((CW, CH)))
    for m in scene["items"]:
        if not (m["start"] <= t < m["end"]):
            continue
        rel = t - m["start"]
        sc, al = _anim(m, rel)
        if m["type"] == "img":
            p = m["path"]
            img = A.video(p, (m["src_start"] or 0) + rel * m["speed"]) if p.lower().endswith((".mp4", ".mov")) \
                else A.image(p)
            if img is None:
                continue
            k = _interp(m["kf"], 1, rel, m["k"]) * sc
            cx = _interp(m["kf"], 2, rel, m["cx"])
            cy = _interp(m["kf"], 3, rel, m["cy"])
            a = _interp(m["kf"], 4, rel, m["alpha"]) * al
            if a <= 0.01:
                continue
            w, h = max(1, int(img.width * k)), max(1, int(img.height * k))
            im = img.resize((w, h), Image.BILINEAR)
            if m.get("rot"):
                im = im.rotate(-m["rot"], expand=True, resample=Image.BILINEAR)
            if a < 0.999:
                im = im.copy()
                im.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
            _paste(canvas, im, cx - im.width / 2, cy - im.height / 2, screen=m.get("blend") == "screen")
        elif m["type"] == "text":
            im = A.text(m)
            if sc != 1.0:
                im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.BILINEAR)
            cx = CW / 2 + m["x"] * CW / 2
            cy = CH / 2 - m["y"] * CH / 2
            _paste(canvas, im, cx - im.width / 2, cy - im.height / 2)
    return canvas.convert("RGB")


def _render_chunk(args):
    scene, f0, f1, out, size = args
    A = Assets()
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s",
                            f"{size[0]}x{size[1]}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset",
                            "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
    for i in range(f0, f1):
        fr = render_frame(scene, A, i / FPS)
        if fr.size != size:
            fr = fr.resize(size, Image.BILINEAR)
        enc.stdin.write(fr.tobytes())
    enc.stdin.close()
    enc.wait()
    return out


# ---------------------------------------------------------------- 音频

def mix_audio(tracks, duration, out):
    """tracks: [(路径, 起点秒, 音量, 素材起点秒, 最长秒或None, 淡出秒)]"""
    args, chains = [], []
    for i, (p, st, vol, src, mx, fade) in enumerate(tracks):
        args += ["-i", p]
        f = f"[{i}:a]atrim=start={src}" + (f":duration={mx}" if mx else "") + ",asetpts=PTS-STARTPTS"
        if fade:
            f += f",afade=t=out:st={max(0, (mx or duration) - fade)}:d={fade}"
        f += f",volume={vol},adelay={int(st * 1000)}:all=1[a{i}]"
        chains.append(f)
    mix = "".join(f"[a{i}]" for i in range(len(tracks)))
    flt = ";".join(chains) + f";{mix}amix=inputs={len(tracks)}:normalize=0:dropout_transition=0," \
                             f"atrim=duration={duration}[out]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args, "-filter_complex", flt, "-map", "[out]", "-ar", "48000",
                    "-ac", "2", out], check=True)
    return out


def render(scene, duration, out, audio_tracks, size=(1080, 1920), workers=6):
    """分段并行渲染。每段是独立的 python 子进程(避免 Windows spawn 重新执行调用方脚本)。"""
    import pickle
    n = int(round(duration * FPS))
    tmp = tempfile.mkdtemp(prefix="render_")
    pk = os.path.join(tmp, "scene.pkl")
    with open(pk, "wb") as f:
        pickle.dump(scene, f)
    step = (n + workers - 1) // workers
    parts, procs = [], []
    for i in range(0, n, step):
        part = os.path.join(tmp, f"part{i:05d}.mp4")
        parts.append(part)
        procs.append(subprocess.Popen([sys.executable, os.path.abspath(__file__), "--chunk", pk, str(i),
                                       str(min(n, i + step)), part, f"{size[0]}x{size[1]}"]))
    if any(p.wait() for p in procs):
        raise RuntimeError("渲染子进程失败")
    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        f.writelines(f"file '{p}'\n" for p in parts)
    wav = mix_audio(audio_tracks, duration, os.path.join(tmp, "mix.wav"))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-i", wav, "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", out], check=True)
    return out


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--chunk":
    import pickle
    _, _, pk, f0, f1, part, wh = sys.argv
    with open(pk, "rb") as f:
        sc = pickle.load(f)
    _render_chunk((sc, int(f0), int(f1), part, tuple(map(int, wh.split("x")))))
