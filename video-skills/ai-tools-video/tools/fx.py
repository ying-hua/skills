"""视频用的图形素材：浮起卡片、流光边框、描边框、贴纸、纯色层等。

全部输出 PNG(带透明) 或 MP4，供剪映草稿引用。
"""
import math
import os
import subprocess

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

import config

FONT_DIR = config.get("FONT_DIR")
DESIGN_DIR = config.get("STICKER_DIR")


def font_black(size):
    """思源黑体(Noto Sans SC) Black 字重，最粗的中文字体。"""
    f = ImageFont.truetype(os.path.join(FONT_DIR, "NotoSansSC-VF.ttf"), size)
    try:
        f.set_variation_by_name("Black")
    except Exception:
        f.set_variation_by_axes([900])
    return f


def font_yahei_bold(size):
    return ImageFont.truetype(os.path.join(FONT_DIR, "msyhbd.ttc"), size)


def rounded_mask(w, h, r, ss=4):
    m = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), r * ss, fill=255)
    return m.resize((w, h), Image.LANCZOS)


def add_shadow(img, blur=22, offset=(0, 12), opacity=0.5, margin=None):
    """给 RGBA 图加柔和投影，返回(新图, 原图在新图中的左上角偏移)。"""
    margin = margin if margin is not None else blur * 2 + max(abs(offset[0]), abs(offset[1]))
    W, H = img.width + margin * 2, img.height + margin * 2
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    a = img.split()[3].point(lambda v: int(v * opacity))
    sh = Image.new("RGBA", img.size, (0, 0, 0, 255))
    sh.putalpha(a)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.paste(sh, (margin + offset[0], margin + offset[1]))
    out = Image.alpha_composite(out, layer.filter(ImageFilter.GaussianBlur(blur)))
    out = Image.alpha_composite(out, _placed(img, (W, H), (margin, margin)))
    return out, (margin, margin)


def _placed(img, size, pos):
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    layer.paste(img, pos, img)
    return layer


# ---------------------------------------------------------------- 浮起卡片

def make_card(src_path, box, out, pad=16, radius=16, border=0, border_color=(255, 255, 255), shadow=True,
              upscale=1.0):
    """从截图中裁出 box(x0,y0,x1,y1) 区域，做成圆角白卡片(带投影)。

    返回 dict: png 尺寸、卡片本体尺寸、源 box 左上角在 png 中的位置、upscale 比例。
    """
    src = Image.open(src_path).convert("RGB")
    x0, y0, x1, y1 = box
    crop = src.crop((x0 - pad, y0 - pad, x1 + pad, y1 + pad))
    if upscale != 1.0:
        crop = crop.resize((round(crop.width * upscale), round(crop.height * upscale)), Image.LANCZOS)
    cw, ch = crop.width + border * 2, crop.height + border * 2
    card = Image.new("RGBA", (cw, ch), border_color + (255,))
    card.paste(crop, (border, border))
    card.putalpha(rounded_mask(cw, ch, radius))
    if shadow:
        img, (mx, my) = add_shadow(card, blur=20, offset=(0, 14), opacity=0.55)
    else:
        img, (mx, my) = card, (0, 0)
    img.save(out)
    return {
        "png": out, "w": img.width, "h": img.height, "card_w": cw, "card_h": ch,
        "card_off": (mx, my), "box_off": (mx + border + pad * upscale, my + border + pad * upscale),
        "upscale": upscale, "radius": radius,
    }


# ---------------------------------------------------------------- 流光边框

def _rrect_path(x0, y0, x1, y1, r, step=2.0):
    """圆角矩形的顺时针等距采样点。"""
    pts = []

    def seg(ax, ay, bx, by):
        n = max(2, int(math.hypot(bx - ax, by - ay) / step))
        for i in range(n):
            t = i / n
            pts.append((ax + (bx - ax) * t, ay + (by - ay) * t))

    def arc(cx, cy, a0, a1):
        n = max(4, int(r * abs(a1 - a0) / step))
        for i in range(n):
            a = a0 + (a1 - a0) * i / n
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))

    seg(x0 + r, y0, x1 - r, y0)
    arc(x1 - r, y0 + r, -math.pi / 2, 0)
    seg(x1, y0 + r, x1, y1 - r)
    arc(x1 - r, y1 - r, 0, math.pi / 2)
    seg(x1 - r, y1, x0 + r, y1)
    arc(x0 + r, y1 - r, math.pi / 2, math.pi)
    seg(x0, y1 - r, x0, y0 + r)
    arc(x0 + r, y0 + r, math.pi, 1.5 * math.pi)
    return np.array(pts)


def make_neon(card_w, card_h, radius, out, duration=2.0, fps=30, margin=70, color=(255, 40, 170),
              loop=1.5, comets=2, tail=0.30, width=6, fade_in=0.25, fade_out=0.25, gap=4):
    """黑底流光视频：两道彩色光沿圆角矩形边缘环绕(剪映里用「滤色」混合叠在卡片上)。

    画布 = 卡片尺寸 + margin*2，中心与卡片中心重合。返回画布尺寸。
    """
    W, H = card_w + margin * 2, card_h + margin * 2
    W += W % 2
    H += H % 2
    x0, y0 = margin - gap, margin - gap
    x1, y1 = margin + card_w + gap, margin + card_h + gap
    path = _rrect_path(x0, y0, x1, y1, radius + gap)
    n = len(path)
    col = np.array(color, dtype=np.float32)
    proc = subprocess.Popen([
        "ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps),
        "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "14", "-pix_fmt", "yuv420p", out,
    ], stdin=subprocess.PIPE)
    frames = int(round(duration * fps))
    tail_n = int(n * tail)
    for f in range(frames):
        t = f / fps
        env = min(1.0, t / fade_in) if fade_in > 0 else 1.0
        env *= min(1.0, (duration - t) / fade_out) if fade_out > 0 else 1.0
        core = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(core)
        # 常亮的细描边(很淡)
        d.line([tuple(p) for p in path] + [tuple(path[0])], fill=40, width=2)
        for c in range(comets):
            head = int(((t / loop + c / comets) % 1.0) * n)
            for k in range(tail_n, 0, -1):
                i0, i1 = (head - k) % n, (head - k + 1) % n
                v = (1 - k / tail_n) ** 1.6
                d.line([tuple(path[i0]), tuple(path[i1])], fill=int(255 * v), width=width)
            hx, hy = path[head]
            d.ellipse((hx - width, hy - width, hx + width, hy + width), fill=255)
        a = np.asarray(core, dtype=np.float32) / 255.0
        g1 = np.asarray(core.filter(ImageFilter.GaussianBlur(8)), dtype=np.float32) / 255.0
        g2 = np.asarray(core.filter(ImageFilter.GaussianBlur(24)), dtype=np.float32) / 255.0
        glow = (g1 * 2.4 + g2 * 3.2)[..., None] * col + (a ** 1.5)[..., None] * (col * 0.55 + 255 * 0.45)
        frame = np.clip(glow * env, 0, 255).astype(np.uint8)
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    proc.wait()
    return {"mp4": out, "w": W, "h": H}


# ---------------------------------------------------------------- 简单图形

def make_solid(out, color=(0, 0, 0), w=1080, h=1920):
    Image.new("RGB", (w, h), color).save(out)
    return out


def make_outline(out, w, h, color=(255, 80, 30), stroke=8, radius=14, margin=12, dashed=False):
    """描边框(透明底)，w/h 为框内尺寸(像素)。返回 png 尺寸和框中心偏移。"""
    ss = 3
    W, H = (w + 2 * margin) * ss, (h + 2 * margin) * ss
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    box = (margin * ss, margin * ss, W - margin * ss, H - margin * ss)
    if not dashed:
        d.rounded_rectangle(box, radius * ss, outline=color + (255,), width=stroke * ss)
    else:
        path = _rrect_path(*box, radius * ss, step=1.0)
        dash, gapl = 22 * ss, 12 * ss
        L = 0
        for i in range(len(path) - 1):
            if (L % (dash + gapl)) < dash:
                d.line([tuple(path[i]), tuple(path[i + 1])], fill=color + (255,), width=stroke * ss)
            L += 1.0
    img = img.resize((W // ss, H // ss), Image.LANCZOS)
    img.save(out)
    return {"png": out, "w": img.width, "h": img.height}


def make_spot(src_path, box, k, out, pad=22, radius=26, gap=16, color=(240, 30, 60), stroke=14, dash=44,
              gap_len=28):
    """聚焦框(用户 2026-10-14 参考小W)：box 区域做成白底圆角卡片 + 外圈红色粗虚线圆角框，透明底 PNG。

    直接按画布分辨率生成(k=画布像素/素材像素)，虚线放大后不会糊。pad=元素到卡片边的留白(素材像素)，
    gap=卡片到虚线的距离(画布像素)。返回 png 尺寸；png 中心 = box 中心。
    """
    src = Image.open(src_path).convert("RGB")
    x0, y0, x1, y1 = box
    crop = src.crop((x0 - pad, y0 - pad, x1 + pad, y1 + pad))
    cw, ch = round(crop.width * k), round(crop.height * k)
    crop = crop.resize((cw, ch), Image.LANCZOS)
    m = gap + stroke + 26  # 外边距，留给虚线和投影
    W, H = cw + 2 * m, ch + 2 * m
    card = Image.new("RGBA", (cw, ch), (255, 255, 255, 255))
    card.paste(crop, (0, 0))
    card.putalpha(rounded_mask(cw, ch, radius))
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh.paste((0, 0, 0, 120), (m, m + 10), rounded_mask(cw, ch, radius))
    img = sh.filter(ImageFilter.GaussianBlur(14))
    img.alpha_composite(card, (m, m))
    ss = 3
    ring = Image.new("RGBA", (W * ss, H * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(ring)
    o = (m - gap - stroke / 2) * ss
    path = _rrect_path(o, o, W * ss - o, H * ss - o, (radius + gap + stroke / 2) * ss, step=1.0)
    L, period = 0.0, (dash + gap_len) * ss
    for i in range(len(path) - 1):
        if L % period < dash * ss:
            d.line([tuple(path[i]), tuple(path[i + 1])], fill=color + (255,), width=stroke * ss)
        L += 1.0
    ring = ring.resize((W, H), Image.LANCZOS)
    img.alpha_composite(ring)
    img.save(out)
    return {"png": out, "w": W, "h": H}


def make_burst(out, color=(255, 214, 0), size=220):
    """三道「强调线」贴纸(放在卡片左上角)。"""
    ss = 3
    S = size * ss
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy = S * 0.85, S * 0.85
    for ang in (-160, -125, -90):
        a = math.radians(ang)
        r0, r1 = S * 0.30, S * 0.70
        d.line([(cx + r0 * math.cos(a), cy + r0 * math.sin(a)), (cx + r1 * math.cos(a), cy + r1 * math.sin(a))],
               fill=color + (255,), width=int(S * 0.075))
        for r in (r0, r1):
            x, y = cx + r * math.cos(a), cy + r * math.sin(a)
            w = S * 0.0375
            d.ellipse((x - w, y - w, x + w, y + w), fill=color + (255,))
    img = img.resize((size, size), Image.LANCZOS)
    img.save(out)
    return out


# ---------------------------------------------------------------- 贴纸

def _text_layer(text, font, fill, stroke=0, stroke_fill=(255, 255, 255)):
    bbox = font.getbbox(text, stroke_width=stroke)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((-bbox[0], -bbox[1]), text, font=font, fill=fill, stroke_width=stroke,
                             stroke_fill=stroke_fill)
    return img


def _gradient(w, h, c0, c1, vertical=False):
    t = np.linspace(0, 1, h if vertical else w, dtype=np.float32)
    g = np.array(c0, np.float32)[None] * (1 - t[:, None]) + np.array(c1, np.float32)[None] * t[:, None]
    arr = np.repeat(g[:, None, :], w, 1) if vertical else np.repeat(g[None, :, :], h, 0)
    return Image.fromarray(arr.astype(np.uint8), "RGB")


def gradient_text(text, size, c0=(40, 160, 255), c1=(190, 70, 255), stroke=14, vertical_grad=False):
    """渐变填充 + 白色粗描边的大字(类似 Figma 里的「非常好用」)。"""
    f = font_black(size)
    outline = _text_layer(text, f, (255, 255, 255, 255), stroke, (255, 255, 255))
    fill_mask = _text_layer(text, f, (255, 255, 255, 255), 0).split()[3]
    grad = _gradient(fill_mask.width, fill_mask.height, c0, c1, vertical_grad).convert("RGBA")
    grad.putalpha(fill_mask)
    ox = (outline.width - fill_mask.width) // 2
    oy = (outline.height - fill_mask.height) // 2
    outline.paste(grad, (ox, oy), grad)
    return outline


def sticker_wow(lines, out, emoji=None, emoji_scale=0.55, c0=(40, 160, 255), c1=(190, 70, 255), size=150,
                emoji_pos="center"):
    """多行渐变大字 + 表情(黄脸)。lines: ["非常", "好用"]；emoji_pos: center 压在字中间 / corner 放在左下角。"""
    layers = [gradient_text(l, size, c0, c1) for l in lines]
    W = max(l.width for l in layers)
    H = sum(l.height for l in layers) - int(size * 0.12) * (len(layers) - 1)
    img = Image.new("RGBA", (W + 40, H + 40), (0, 0, 0, 0))
    y = 20
    for l in layers:
        img.alpha_composite(l, ((img.width - l.width) // 2, y))
        y += l.height - int(size * 0.12)
    if emoji:
        e = Image.open(os.path.join(DESIGN_DIR, emoji)).convert("RGBA")
        es = int(img.height * emoji_scale)
        e = e.resize((int(e.width * es / e.height), es), Image.LANCZOS)
        if emoji_pos == "corner":
            big = Image.new("RGBA", (img.width + int(e.width * 0.55), img.height + int(e.height * 0.35)),
                            (0, 0, 0, 0))
            big.alpha_composite(img, (big.width - img.width, 0))
            big.alpha_composite(e, (0, big.height - e.height))
            img = big
        else:
            img.alpha_composite(e, ((img.width - e.width) // 2, (img.height - e.height) // 2))
    img, _ = add_shadow(img, blur=12, offset=(0, 8), opacity=0.45)
    img.save(out)
    return {"png": out, "w": img.width, "h": img.height}


def sticker_tag(text, out, bg=(255, 84, 84), fg=(255, 255, 255), size=96, emoji=None, tail="right"):
    """像素风对话框标签(类似 Figma 里的「调用记录」)：红底白字 + 白色描边 + 小尾巴。"""
    f = font_black(size)
    tl = _text_layer(text, f, fg + (255,), 6, (190, 40, 40))
    padx, pady, step = int(size * 0.45), int(size * 0.30), int(size * 0.12)
    bw, bh = tl.width + padx * 2, tl.height + pady * 2
    W, H = bw + step * 4 + 40, bh + int(size * 0.75) + step * 4
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ox, oy = step * 2 + 10, step * 2 + 10

    def body(col, grow):
        # 阶梯状(像素风)的圆角：三层矩形叠加
        for i in range(3):
            g = grow + (2 - i) * 0
            d.rectangle((ox - g + step * (2 - i), oy - g + step * i, ox + bw + g - step * (2 - i),
                         oy + bh + g - step * i), fill=col)
        tx = ox + bw - int(size * 0.9) if tail == "right" else ox + int(size * 0.5)
        tip = (tx + int(size * 0.75), oy + bh + int(size * 0.6) + grow) if tail == "right" else \
            (tx - int(size * 0.35), oy + bh + int(size * 0.6) + grow)
        d.polygon([(tx - grow, oy + bh - 2), (tx + int(size * 0.5) + grow, oy + bh - 2), tip], fill=col)

    body((255, 255, 255, 255), step)
    body(bg + (255,), 0)
    img.alpha_composite(tl, (ox + padx, oy + pady - int(size * 0.06)))
    if emoji:
        e = Image.open(os.path.join(DESIGN_DIR, emoji)).convert("RGBA")
        es = int(bh * 1.25)
        e = e.resize((int(e.width * es / e.height), es), Image.LANCZOS)
        big = Image.new("RGBA", (img.width + e.width // 2, img.height + e.height // 3), (0, 0, 0, 0))
        big.alpha_composite(img, (0, e.height // 3))
        big.alpha_composite(e, (big.width - e.width, 0))
        img = big
    img, _ = add_shadow(img, blur=10, offset=(0, 8), opacity=0.4)
    img.save(out)
    return {"png": out, "w": img.width, "h": img.height}


def title_text(text, out, size, fill=(255, 255, 255), stroke=0, stroke_fill=(0, 0, 0), shadow=True):
    """片头大字(纯色)。"""
    f = font_black(size)
    img = _text_layer(text, f, fill + (255,), stroke, stroke_fill)
    if shadow:
        img, _ = add_shadow(img, blur=10, offset=(0, 6), opacity=0.6)
    img.save(out)
    return {"png": out, "w": img.width, "h": img.height}


def pill_text(text, out, size, bg=(255, 225, 0), fg=(20, 20, 20), radius=None):
    """圆角底色标签，例如「第29期」。"""
    f = font_black(size)
    tl = _text_layer(text, f, fg + (255,))
    padx, pady = int(size * 0.32), int(size * 0.22)
    w, h = tl.width + padx * 2, tl.height + pady * 2
    img = Image.new("RGBA", (w, h), bg + (255,))
    img.putalpha(rounded_mask(w, h, radius if radius is not None else int(h * 0.22)))
    img.alpha_composite(tl, (padx, pady - int(size * 0.04)))
    img.save(out)
    return {"png": out, "w": img.width, "h": img.height}


def framed_image(src, out, max_w=900, border=14, radius=26, dashed_color=None):
    """片头卡片：图片加白边圆角 + 投影。"""
    im = Image.open(src).convert("RGB")
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
    cw, ch = im.width + border * 2, im.height + border * 2
    card = Image.new("RGBA", (cw, ch), (255, 255, 255, 255))
    card.paste(im, (border, border))
    card.putalpha(rounded_mask(cw, ch, radius))
    img, _ = add_shadow(card, blur=26, offset=(0, 18), opacity=0.6)
    img.save(out)
    return {"png": out, "w": img.width, "h": img.height}


def blur_risky(png, risky, out, pad=8, radius=14):
    """局部模糊易被限流的区域(用户 2026-10-16：链接、注册/登录/付费/赞助字眼、广告横幅)。

    risky: capture.mjs 输出的列表 [{box, tile?, ...}] 或其 json 路径(readme.json / repo.json 的 risky 字段，
    或单独的 risky 列表文件)；带 tile 的只取文件名等于 png 的。返回模糊后的新 PNG 路径(镜头/聚焦框都用它)。
    """
    import json
    if isinstance(risky, str):
        d = json.load(open(risky, encoding="utf-8"))
        risky = d.get("risky", []) if isinstance(d, dict) else d
    name = os.path.basename(png)
    boxes = [r["box"] for r in risky if r.get("tile", name) == name]
    im = Image.open(png).convert("RGB")
    for x0, y0, x1, y1 in boxes:
        b = (max(0, x0 - pad), max(0, y0 - pad), min(im.width, x1 + pad), min(im.height, y1 + pad))
        if b[2] <= b[0] or b[3] <= b[1]:
            continue
        region = im.crop(b)
        # 先缩小再放大 + 高斯，字完全认不出但保留色块(和剪映模糊特效观感一致)
        small = region.resize((max(1, region.width // 6), max(1, region.height // 6)), Image.BILINEAR)
        region = small.resize(region.size, Image.BILINEAR).filter(ImageFilter.GaussianBlur(radius))
        im.paste(region, b[:2])
    im.save(out)
    return out
