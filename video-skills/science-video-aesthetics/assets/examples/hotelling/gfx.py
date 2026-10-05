"""Drawing helpers: easing, keyframes, colours, cairo primitives, PIL-text -> cairo."""
import math
import functools
import numpy as np
import cairo
from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
FPS = 30

F_TITLE = 'C:/Windows/Fonts/STHUPO.TTF'
F_BODY = 'C:/Windows/Fonts/msyhbd.ttc'
F_LIGHT = 'C:/Windows/Fonts/msyh.ttc'
F_NUM = 'C:/Windows/Fonts/Rubik-Bold.ttf'


def hexc(h, a=1.0):
    h = h.lstrip('#')
    return (int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255, a)


# palette
SAND = hexc('#F3DCAA')
SAND_D = hexc('#E8C88E')
WET = hexc('#D9B784')
SEA_DEEP = hexc('#17809A')
SEA = hexc('#36B5C2')
SEA_SH = hexc('#7FD9D2')
FOAM = hexc('#FFFDF5')
CORAL = hexc('#F2766B')
CORAL_D = hexc('#C9544B')
MINT = hexc('#4FC3A1')
MINT_D = hexc('#2E9A7C')
BUTTER = hexc('#FFD25E')
NAVY = hexc('#2B3A55')
CREAM = hexc('#FFF6E5')
PINK = hexc('#F7B9C4')
SKY = hexc('#A8DCEB')
RED = hexc('#E5484D')


def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def lerp(a, b, t):
    return a + (b - a) * t


def lerpc(c1, c2, t):
    return tuple(lerp(a, b, t) for a, b in zip(c1, c2))


def smooth(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def ease_io(t):
    t = clamp(t)
    return 4 * t ** 3 if t < .5 else 1 - (-2 * t + 2) ** 3 / 2


def ease_out(t):
    t = clamp(t)
    return 1 - (1 - t) ** 3


def ease_in(t):
    t = clamp(t)
    return t ** 3


def back_out(t, s=1.70158):
    t = clamp(t)
    t -= 1
    return t * t * ((s + 1) * t + s) + 1


def elastic(t):
    t = clamp(t)
    if t in (0, 1):
        return t
    return 2 ** (-10 * t) * math.sin((t * 10 - .75) * 2 * math.pi / 3) + 1


def win(t, a, b, fi=0.3, fo=0.3):
    """1 inside [a,b] with fades."""
    if t < a or t > b:
        return 0.0
    return min(smooth((t - a) / fi) if fi > 0 else 1, smooth((b - t) / fo) if fo > 0 else 1)


EASES = {'io': ease_io, 'out': ease_out, 'in': ease_in, 'lin': clamp, 'back': back_out, 'smooth': smooth}


class Track:
    """Piecewise keyframes: list of (t0, t1, v_end, ease). Value holds between moves."""

    def __init__(self, v0, moves):
        self.v0 = v0
        self.moves = sorted(moves, key=lambda m: m[0])

    def __call__(self, t):
        v = self.v0
        for t0, t1, v1, e in self.moves:
            if t < t0:
                break
            if t >= t1:
                v = v1
            else:
                return lerp(v, v1, EASES[e]((t - t0) / (t1 - t0)))
        return v

    def moving(self, t):
        for t0, t1, v1, e in self.moves:
            if t0 <= t < t1:
                return True
        return False


# ---------------------------------------------------------------- cairo shapes
def rrect(ctx, x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    ctx.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    ctx.close_path()


def circle(ctx, x, y, r):
    ctx.new_sub_path()
    ctx.arc(x, y, r, 0, 2 * math.pi)


def ellipse(ctx, x, y, rx, ry, rot=0):
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(rot)
    ctx.scale(rx, ry)
    ctx.new_sub_path()
    ctx.arc(0, 0, 1, 0, 2 * math.pi)
    ctx.restore()


def src(ctx, c, a=None):
    if a is None:
        ctx.set_source_rgba(*c) if len(c) == 4 else ctx.set_source_rgb(*c)
    else:
        ctx.set_source_rgba(c[0], c[1], c[2], (c[3] if len(c) == 4 else 1) * a)


def fill(ctx, c, a=None):
    src(ctx, c, a)
    ctx.fill()


def dashed_line(ctx, x0, y0, x1, y1, c, w=3, dash=(10, 8), off=0, a=1):
    ctx.save()
    ctx.set_dash(dash, off)
    ctx.set_line_width(w)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.move_to(x0, y0)
    ctx.line_to(x1, y1)
    src(ctx, c, a)
    ctx.stroke()
    ctx.restore()


# ---------------------------------------------------------------- text
@functools.lru_cache(maxsize=64)
def _font(path, size):
    return ImageFont.truetype(path, size)


@functools.lru_cache(maxsize=1024)
def text_surface(text, font=F_BODY, size=48, color=(1, 1, 1, 1), stroke=0, stroke_color=(0, 0, 0, 1), spacing=0.25,
                 shadow=0):
    """Render (multi-line, centered) text with PIL; return cairo ImageSurface + size."""
    f = _font(font, size)
    lines = text.split('\n')
    asc, desc = f.getmetrics()
    lh = int((asc + desc) * (1 + spacing))
    widths = [f.getlength(l) for l in lines]
    pad = stroke + 4 + shadow
    w = int(max(widths) + pad * 2 + 2)
    h = int(lh * len(lines) - (lh - asc - desc) + pad * 2 + 2)
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c255 = tuple(int(v * 255) for v in color[:3]) + (255,)
    s255 = tuple(int(v * 255) for v in stroke_color[:3]) + (255,)
    for i, l in enumerate(lines):
        x = pad + (max(widths) - widths[i]) / 2
        y = pad + i * lh
        if shadow:
            d.text((x + shadow, y + shadow), l, font=f, fill=s255, stroke_width=stroke, stroke_fill=s255)
        d.text((x, y), l, font=f, fill=c255, stroke_width=stroke, stroke_fill=s255)
    return pil_to_surface(img), w, h


def pil_to_surface(img):
    a = np.asarray(img.convert('RGBA')).astype(np.float32)
    al = a[..., 3:4] / 255
    pm = np.concatenate([a[..., :3] * al, a[..., 3:4]], -1)
    bgra = pm[..., [2, 1, 0, 3]].round().astype(np.uint8)
    h, w = bgra.shape[:2]
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    stride = surf.get_stride()
    buf = np.ndarray((h, stride // 4, 4), np.uint8, surf.get_data())
    buf[:, :w] = bgra
    surf.mark_dirty()
    return surf


def text(ctx, s, x, y, size=48, font=F_BODY, color=NAVY, alpha=1.0, anchor='c', scale=1.0, rot=0.0, **kw):
    if alpha <= 0.003 or not s or abs(scale) < 1e-3:
        return 0, 0
    surf, w, h = text_surface(s, font, size, tuple(color), **kw)
    ctx.save()
    ctx.translate(x, y)
    if rot:
        ctx.rotate(rot)
    if scale != 1:
        ctx.scale(scale, scale)
    ox = {'c': -w / 2, 'l': 0, 'r': -w}[anchor[0]]
    oy = -h / 2 if len(anchor) == 1 else {'t': 0, 'm': -h / 2, 'b': -h}[anchor[1]]
    ctx.set_source_surface(surf, ox, oy)
    ctx.paint_with_alpha(alpha)
    ctx.restore()
    return w, h


def text_size(s, size=48, font=F_BODY, **kw):
    _, w, h = text_surface(s, font, size, tuple(NAVY), **kw)
    return w, h


def pill(ctx, s, x, y, size=34, font=F_BODY, fg=NAVY, bg=CREAM, alpha=1.0, padx=26, pady=12, scale=1.0, border=None,
         shadow=True):
    if alpha <= 0.003 or abs(scale) < 1e-3:
        return
    w, h = text_size(s, size, font)
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(scale, scale)
    bw, bh = w + padx * 2 - 8, h + pady * 2 - 8
    if shadow:
        rrect(ctx, -bw / 2 + 4, -bh / 2 + 6, bw, bh, bh / 2)
        fill(ctx, NAVY, 0.22 * alpha)
    rrect(ctx, -bw / 2, -bh / 2, bw, bh, bh / 2)
    fill(ctx, bg, alpha)
    if border:
        rrect(ctx, -bw / 2, -bh / 2, bw, bh, bh / 2)
        ctx.set_line_width(4)
        src(ctx, border, alpha)
        ctx.stroke()
    text(ctx, s, 0, 0, size, font, fg, alpha)
    ctx.restore()
