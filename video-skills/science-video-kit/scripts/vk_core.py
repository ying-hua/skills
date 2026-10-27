"""vk_core - style-neutral 2D drawing core for procedural science videos (cairo + cv2 + PIL).

  Canvas      cairo base surface + half-res EMISSION surface (cv.g, additive) that gets bloomed in finish()
  helpers     easing (ss, ease_out, ease_io, back_out), win() visibility windows, hrand() deterministic hash, fbm noise
  effects     tracer (glowing streak), muzzle (star flash + smoke), impact (dust burst + shock ring), dust_motes,
              reticle, dashed_line, arrow_head, rrect, panel
  text        add_text(cv, '[a]colored[/] markup', ...) queued and rasterised in finish(); CJK + latin font mixing;
              cv.text_boxes / text_in_zones() report where text ink landed (cover safe-zone checks)
  compose     group(cv, fn, a): draw a sub-scene on both layers and fade it as one piece
  post        finish(cv, idx) -> uint8 HxWx3: bloom, text, flash, soft shoulder, chromatic aberration, vignette, grain

Style lives in YOUR project: set_fonts(), set_tags(), palette constants, backgrounds, characters.
Frame size: set env VK_W / VK_H before importing (default 1920x1080; 1080x1920 for vertical).
"""
import functools, math, os
import numpy as np
import cairo, cv2
from PIL import Image, ImageDraw, ImageFont

W, H = int(os.environ.get('VK_W', 1920)), int(os.environ.get('VK_H', 1080))
TAU = math.tau

# ---------------------------------------------------------------- neutral default palette (0..1 rgb) - override per project
INK = (0.06, 0.05, 0.07)
CREAM = (0.97, 0.94, 0.88)
DIMC = (0.70, 0.68, 0.66)
HILITE = (1.0, 0.85, 0.45)


def clamp01(x):
    return min(1.0, max(0.0, x))


def ss(a, b, x):
    t = clamp01((x - a) / (b - a)) if b != a else float(x >= a)
    return t * t * (3 - 2 * t)


def ease_out(x):
    x = clamp01(x)
    return 1 - (1 - x) ** 3


def ease_io(x):
    x = clamp01(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def back_out(x, s=1.9):
    x = clamp01(x)
    return 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2


def lerp(a, b, k):
    return a + (b - a) * k


def lerp2(p, q, k):
    return (p[0] + (q[0] - p[0]) * k, p[1] + (q[1] - p[1]) * k)


def mix(c1, c2, k):
    return tuple(a + (b - a) * k for a, b in zip(c1, c2))


def win(t, t0, t1, fin=0.35, fout=0.35):
    """0..1 visibility window"""
    if t < t0 or t > t1:
        return 0.0
    return min(clamp01((t - t0) / fin) if fin > 0 else 1, clamp01((t1 - t) / fout) if fout > 0 else 1)


def hrand(*a):
    """deterministic hash -> [0,1)"""
    h = 0
    for v in a:
        h = (h * 1000003) ^ int(v * 7919 + 12345)
        h &= 0xFFFFFFFF
    h ^= h >> 15
    h = (h * 2246822519) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 3266489917) & 0xFFFFFFFF
    h ^= h >> 16
    return h / 4294967296.0


# ---------------------------------------------------------------- canvas
class Canvas:
    """Base cairo surface + half-res emission surface (bloomed and added in post)."""

    def __init__(self):
        self.base = cairo.ImageSurface(cairo.FORMAT_RGB24, W, H)
        self.glow = cairo.ImageSurface(cairo.FORMAT_RGB24, W // 2, H // 2)
        self.c = cairo.Context(self.base)
        self.g = cairo.Context(self.glow)
        self.g.scale(0.5, 0.5)
        for c in (self.c, self.g):
            c.set_line_cap(cairo.LINE_CAP_ROUND)
            c.set_line_join(cairo.LINE_JOIN_ROUND)
        self.g.set_operator(cairo.OPERATOR_ADD)
        self.texts = []
        self.flash = 0.0          # additive white-gold flash
        self.shake = (0.0, 0.0)
        self.fade = 1.0           # global brightness multiplier
        self.grain = 1.0
        self.vignette = 1.0
        self.ca = 0.0             # chromatic aberration strength
        self.text_boxes = []      # [(text dict, ink box (x0, y0, x1, y1) px)] filled by finish()

    def both(self):
        return (self.c, self.g)

    def set_cam(self, zoom=1.0, cx=W / 2, cy=H / 2, rot=0.0):
        """world point (cx,cy) appears at screen centre, scaled by zoom."""
        for ctx in (self.c, self.g):
            ctx.save()
            ctx.translate(W / 2 + self.shake[0], H / 2 + self.shake[1])
            ctx.rotate(rot)
            ctx.scale(zoom, zoom)
            ctx.translate(-cx, -cy)

    def reset_cam(self):
        for ctx in (self.c, self.g):
            ctx.restore()


_KEEP = []          # per-frame temporaries: clear with _KEEP.clear() at the end of render_frame
_PERSIST = []       # long-lived cached textures (persist=True): never cleared


def to_surface(img, persist=False):
    """float rgb (h,w,3) 0..1 -> cairo RGB24 surface. The numpy buffer is kept alive in _KEEP (per-frame, clear it
    after finish) or, with persist=True, in _PERSIST (for textures cached at import time and reused every frame)."""
    h, w, _ = img.shape
    a = np.empty((h, w, 4), np.uint8)
    a[..., 0] = np.clip(img[..., 2] * 255, 0, 255)
    a[..., 1] = np.clip(img[..., 1] * 255, 0, 255)
    a[..., 2] = np.clip(img[..., 0] * 255, 0, 255)
    a[..., 3] = 255
    s = cairo.ImageSurface.create_for_data(memoryview(a), cairo.FORMAT_RGB24, w, h)
    (_PERSIST if persist else _KEEP).append(a)
    return s


def to_surface_rgba(img, alpha, persist=False):
    h, w, _ = img.shape
    a = np.empty((h, w, 4), np.uint8)
    al = np.clip(alpha, 0, 1)
    a[..., 0] = np.clip(img[..., 2] * al * 255, 0, 255)
    a[..., 1] = np.clip(img[..., 1] * al * 255, 0, 255)
    a[..., 2] = np.clip(img[..., 0] * al * 255, 0, 255)
    a[..., 3] = np.clip(al * 255, 0, 255)
    s = cairo.ImageSurface.create_for_data(memoryview(a), cairo.FORMAT_ARGB32, w, h)
    (_PERSIST if persist else _KEEP).append(a)
    return s


def paint_img(ctx, surf, x=0, y=0, alpha=1.0, scale=1.0):
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(scale, scale)
    ctx.set_source_surface(surf, 0, 0)
    ctx.get_source().set_filter(cairo.FILTER_BILINEAR)
    if alpha >= 0.999:
        ctx.paint()
    else:
        ctx.paint_with_alpha(alpha)
    ctx.restore()


# ---------------------------------------------------------------- noise
def fbm(h, w, seed=0, octaves=6, base=4, persist=0.55):
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        n = base * 2 ** o
        g = rng.random((int(n * h / max(h, w)) + 2, n + 2)).astype(np.float32)
        out += cv2.resize(g, (w, h), interpolation=cv2.INTER_CUBIC) * amp
        tot += amp
        amp *= persist
    return out / tot


# ---------------------------------------------------------------- generic effects
def tracer(cv, p0, p1, u, col, width=4.0, trail=260, alpha=1.0, head=True):
    """bullet travelling p0->p1 (u in 0..1, may exceed 1 for overshoot)"""
    if alpha <= 0:
        return
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(dx, dy) + 1e-6
    hx, hy = p0[0] + dx * u, p0[1] + dy * u
    tl = min(trail, L * max(u, 0))
    tx, ty = hx - dx / L * tl, hy - dy / L * tl
    for ctx, wmul, amul in ((cv.c, 1.0, 1.0), (cv.g, 3.0, 1.0)):
        lg = cairo.LinearGradient(tx, ty, hx, hy)
        lg.add_color_stop_rgba(0, *col, 0)
        lg.add_color_stop_rgba(1, *mix(col, (1, 1, 0.9), 0.6), alpha * amul)
        ctx.set_source(lg)
        ctx.set_line_width(width * wmul)
        ctx.move_to(tx, ty)
        ctx.line_to(hx, hy)
        ctx.stroke()
    if head:
        cv.c.set_source_rgba(1, 1, 0.92, alpha)
        cv.c.arc(hx, hy, width * 0.9, 0, TAU)
        cv.c.fill()
        cv.g.set_source_rgba(*[v * alpha for v in mix(col, (1, 1, 1), 0.5)], 1)
        cv.g.arc(hx, hy, width * 3, 0, TAU)
        cv.g.fill()
    return hx, hy


def muzzle(cv, p, ang, k, s=1.0, col=(1.0, 0.85, 0.5)):
    """k = time since shot (s)"""
    if k < 0 or k > 0.35:
        return
    e = math.exp(-k * 22)
    c, g = cv.c, cv.g
    for ctx, sc in ((c, 1.0), (g, 1.6)):
        ctx.save()
        ctx.translate(*p)
        ctx.rotate(ang)
        n = 9
        ctx.move_to(0, 0)
        for i in range(n * 2 + 1):
            a = -0.9 + 1.8 * i / (n * 2)
            r = (38 if i % 2 == 0 else 12) * s * sc * (0.6 + 0.8 * hrand(i, p[0]))
            r *= 1.6 if abs(a) < 0.15 and i % 2 == 0 else 1
            ctx.line_to(math.cos(a) * r * (0.5 + e), math.sin(a) * r * (0.5 + e))
        ctx.close_path()
        ctx.set_source_rgba(*col, e)
        ctx.fill()
        ctx.restore()
    # smoke puff
    for i in range(7):
        r = (6 + 30 * ease_out(k / 0.35) * (0.5 + hrand(i, 3))) * s
        a = ang + (hrand(i, 7) - 0.5) * 1.6
        d = (10 + 40 * ease_out(k / 0.35)) * s * hrand(i, 9)
        c.set_source_rgba(0.75, 0.66, 0.6, 0.22 * (1 - k / 0.35))
        c.arc(p[0] + math.cos(a) * d, p[1] + math.sin(a) * d, r, 0, TAU)
        c.fill()


def impact(cv, p, k, col=(0.85, 0.65, 0.45), s=1.0, seed=0, blood=None):
    """dust burst; k = time since impact"""
    if k < 0 or k > 1.2:
        return
    c, g = cv.c, cv.g
    f = ease_out(k / 1.2)
    for i in range(22):
        a = hrand(seed, i) * TAU
        sp = (40 + 120 * hrand(seed, i, 2)) * s
        r = (3 + 9 * hrand(seed, i, 3)) * s * (1 + f)
        d = sp * f
        c.set_source_rgba(*col, 0.5 * (1 - f))
        c.arc(p[0] + math.cos(a) * d, p[1] + math.sin(a) * d, r, 0, TAU)
        c.fill()
    # shock ring
    if k < 0.5:
        rr = 10 + 140 * ease_out(k / 0.5) * s
        for ctx in (c, g):
            ctx.set_line_width(3 * (1 - k / 0.5) + 0.5)
            ctx.set_source_rgba(1, 0.9, 0.7, (1 - k / 0.5) * 0.8)
            ctx.arc(p[0], p[1], rr, 0, TAU)
            ctx.stroke()
    if k < 0.12:
        g.set_source_rgba(1, 0.9, 0.7, 1)
        g.arc(p[0], p[1], 40 * s * (1 - k / 0.12), 0, TAU)
        g.fill()
    if blood is not None:
        for i in range(10):
            a = hrand(seed, i, 5) * TAU
            d = (20 + 50 * hrand(seed, i, 6)) * f * s
            c.set_source_rgba(*blood, 0.8 * (1 - f * 0.5))
            c.arc(p[0] + math.cos(a) * d, p[1] + math.sin(a) * d, 3 * s, 0, TAU)
            c.fill()


def dust_motes(cv, t, n=70, seed=1, wind=(60, -6), col=(1.0, 0.8, 0.55), alpha=0.5, size=2.4, region=(0, 0, W, H)):
    x0, y0, x1, y1 = region
    for i in range(n):
        bx = hrand(seed, i) * (x1 - x0)
        by = hrand(seed, i, 1) * (y1 - y0)
        sp = 0.5 + hrand(seed, i, 2)
        x = x0 + (bx + wind[0] * sp * t) % (x1 - x0)
        y = y0 + (by + wind[1] * sp * t + 14 * math.sin(t * 0.7 + i)) % (y1 - y0)
        r = size * (0.4 + hrand(seed, i, 3))
        a = alpha * (0.3 + 0.7 * hrand(seed, i, 4)) * (0.6 + 0.4 * math.sin(t * 2 + i))
        cv.c.set_source_rgba(*col, a)
        cv.c.arc(x, y, r, 0, TAU)
        cv.c.fill()


def reticle(cv, x, y, r, col, rot=0.0, alpha=1.0, glow=0.6):
    for ctx, gm in ((cv.c, 1.0), (cv.g, glow)):
        if gm <= 0:
            continue
        ctx.save()
        ctx.translate(x, y)
        ctx.rotate(rot)
        ctx.set_line_width(3)
        ctx.set_source_rgba(*[v * (gm if ctx is cv.g else 1) for v in col], alpha if ctx is cv.c else 1)
        for i in range(4):
            a0 = i * TAU / 4 + 0.25
            ctx.arc(0, 0, r, a0, a0 + TAU / 4 - 0.5)
            ctx.new_sub_path()
        for i in range(4):
            a = i * TAU / 4
            ctx.move_to(math.cos(a) * r * 0.75, math.sin(a) * r * 0.75)
            ctx.line_to(math.cos(a) * r * 1.25, math.sin(a) * r * 1.25)
        ctx.stroke()
        ctx.restore()


def dashed_line(cv, p0, p1, col, alpha=1.0, width=2.5, dash=(14, 10), offset=0.0, k=1.0, glow=0.0):
    if alpha <= 0 or k <= 0:
        return
    q = lerp2(p0, p1, k)
    c = cv.c
    c.save()
    c.set_dash(dash, offset)
    c.set_line_width(width)
    c.set_source_rgba(*col, alpha)
    c.move_to(*p0)
    c.line_to(*q)
    c.stroke()
    c.restore()
    if glow > 0:
        cv.g.save()
        cv.g.set_dash(dash, offset)
        cv.g.set_line_width(width * 2.5)
        cv.g.set_source_rgba(*[v * glow * alpha for v in col], 1)
        cv.g.move_to(*p0)
        cv.g.line_to(*q)
        cv.g.stroke()
        cv.g.restore()


def arrow_head(ctx, p, ang, size, col, alpha=1.0):
    ctx.save()
    ctx.translate(*p)
    ctx.rotate(ang)
    ctx.move_to(0, 0)
    ctx.line_to(-size, -size * 0.55)
    ctx.line_to(-size * 0.7, 0)
    ctx.line_to(-size, size * 0.55)
    ctx.close_path()
    ctx.set_source_rgba(*col, alpha)
    ctx.fill()
    ctx.restore()


def rrect(ctx, x, y, w, h, r):
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -TAU / 4, 0)
    ctx.arc(x + w - r, y + h - r, r, 0, TAU / 4)
    ctx.arc(x + r, y + h - r, r, TAU / 4, TAU / 2)
    ctx.arc(x + r, y + r, r, TAU / 2, TAU * 3 / 4)
    ctx.close_path()


def panel(cv, x, y, w, h, alpha=1.0, col=None, fill=(0.06, 0.025, 0.04), fill_a=0.72, r=10):
    col = col or CREAM
    if alpha <= 0:
        return
    c = cv.c
    rrect(c, x, y, w, h, r)
    c.set_source_rgba(*fill, fill_a * alpha)
    c.fill_preserve()
    c.set_line_width(1.5)
    c.set_source_rgba(*col, 0.35 * alpha)
    c.stroke()


# ---------------------------------------------------------------- typography (PIL glyphs, composited in post)
FONT_CJK = 'C:/Windows/Fonts/NotoSerifSC-VF.ttf'       # variable font: weight axis honoured
FONT_CJK_SANS = 'C:/Windows/Fonts/NotoSansSC-VF.ttf'
FONT_LAT = 'C:/Windows/Fonts/georgiab.ttf'             # latin/digits when weight >= 700
FONT_LAT2 = 'C:/Windows/Fonts/georgia.ttf'             # latin/digits when weight < 700
LAT_SCALE = 1.0


def set_fonts(cjk=None, cjk_sans=None, lat=None, lat2=None, lat_scale=None):
    """pick a type pairing per project (e.g. Rockwell for western, Bahnschrift for tech, Georgia for classic)"""
    g = globals()
    for k, v in (('FONT_CJK', cjk), ('FONT_CJK_SANS', cjk_sans), ('FONT_LAT', lat), ('FONT_LAT2', lat2),
                 ('LAT_SCALE', lat_scale)):
        if v is not None:
            g[k] = v
    _font.cache_clear()
    _resolve.cache_clear()
    glyph.cache_clear()


def set_tags(tags):
    """markup colour tags, e.g. set_tags({'a': TEAL, 'b': GOLD}) -> '[a]text[/]'"""
    TAGS.clear()
    TAGS.update(tags)


_FALLBACK = {
    'cjk': ['/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc', '/usr/share/fonts/noto-cjk/NotoSerifCJK-Bold.ttc',
            '/System/Library/Fonts/Supplemental/Songti.ttc', '/System/Library/Fonts/PingFang.ttc',
            'C:/Windows/Fonts/simhei.ttf'],
    'lat': ['/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf', '/System/Library/Fonts/Supplemental/Georgia Bold.ttf',
            'C:/Windows/Fonts/arialbd.ttf'],
}


@functools.lru_cache(64)
def _resolve(path):
    """use the configured font if present, else fc-match / common CJK & latin fonts on Linux, macOS, Windows"""
    if os.path.exists(path):
        return path
    import shutil, subprocess
    name = os.path.splitext(os.path.basename(path))[0]
    if shutil.which('fc-match'):
        r = subprocess.run(['fc-match', '-f', '%{file}', name], capture_output=True, text=True).stdout.strip()
        if r and os.path.exists(r):
            return r
    kind = 'cjk' if path in (FONT_CJK, FONT_CJK_SANS) else 'lat'
    for p in _FALLBACK[kind]:
        if os.path.exists(p):
            return p
    raise FileNotFoundError(f'font {path} not found; call vk_core.set_fonts(...) with fonts installed on this machine')


@functools.lru_cache(64)
def _font(path, size, weight):
    f = ImageFont.truetype(_resolve(path), int(size))
    if 'VF' in path:
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
    return f


@functools.lru_cache(4096)
def has_glyph(path, ch):
    """does the font at `path` contain a real glyph for ch? (a missing one renders the .notdef 'tofu' box)"""
    if ch.isspace():
        return True
    f = _font(path, 32, 400)
    probe = f.getmask(ch)
    tofu = f.getmask('􏿽')
    return not (probe.size == tofu.size and bytes(probe) == bytes(tofu))


SYMBOL_FALLBACK = ['C:/Windows/Fonts/seguisym.ttf', 'C:/Windows/Fonts/cambria.ttc', 'C:/Windows/Fonts/segoeui.ttf',
                   'C:/Windows/Fonts/arial.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                   '/System/Library/Fonts/Supplemental/Arial Unicode.ttf']


@functools.lru_cache(8192)
def _font_choice(ch, size, weight, sans, font=None):
    """(path, size, weight) of the first font in the chain that really has ch: font override -> latin/CJK default
    (script order) -> the other default -> SYMBOL_FALLBACK. None if nothing has it."""
    lat = (FONT_LAT if weight >= 700 else FONT_LAT2, size * LAT_SCALE, 0)
    cjk = (FONT_CJK_SANS if sans else FONT_CJK, size, weight)
    order = [lat, cjk] if (ord(ch) < 0x2000 and ch not in '·×—…') else [cjk, lat]
    if font:
        order.insert(0, (font, size, weight))
    order += [(p, size, 400) for p in SYMBOL_FALLBACK if os.path.exists(p)]
    for c in order:
        try:
            if has_glyph(c[0], ch):
                return c
        except OSError:
            continue
    return None


def _font_for(ch, size, weight, sans, font=None):
    c = _font_choice(ch, size, weight, sans, font)
    if c is None:          # nothing has it: keep the old behaviour (tofu from the primary font)
        if font:
            return _font(font, size, weight)
        if ord(ch) < 0x2000 and ch not in '·×—…':
            return _font(FONT_LAT if weight >= 700 else FONT_LAT2, size * LAT_SCALE, 0)
        return _font(FONT_CJK_SANS if sans else FONT_CJK, size, weight)
    return _font(*c)


@functools.lru_cache(64)
def math_img(tex, size, color=(1.0, 1.0, 1.0), fontset='stix'):
    """render a LaTeX-subset formula (matplotlib mathtext, no TeX install needed) on a transparent background
    -> (rgb float (h,w,3), alpha (h,w)). size = font size in px (same scale as add_text); tex without the $...$."""
    import io as _io
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    fig = Figure(figsize=(1, 1), dpi=100)
    FigureCanvasAgg(fig)
    fig.text(0, 0, f'${tex}$', fontsize=size * 0.72, color=tuple(color), math_fontfamily=fontset)
    buf = _io.BytesIO()
    fig.savefig(buf, dpi=100, format='png', transparent=True, bbox_inches='tight', pad_inches=0.06)
    buf.seek(0)
    im = np.asarray(Image.open(buf).convert('RGBA'), np.float32) / 255.0
    a = np.ascontiguousarray(im[..., 3])
    rgb = np.empty(im.shape[:2] + (3,), np.float32)
    rgb[:] = np.array(color, np.float32)          # flat ink colour; coverage lives in alpha
    return rgb, a


def add_math(cv, tex, x, y, size=48, color=None, alpha=1.0, anchor='m', glow=0.0, fontset='stix'):
    """paint a formula with real sub/superscripts, fractions and roots onto the base layer, centred at (x, y)
    (anchor 'l'/'r' align left/right edge). Drawn immediately (not in finish), so call it in draw order."""
    if alpha <= 0.004:
        return
    rgb, a = math_img(tex, int(size), tuple(color or CREAM), fontset)
    h, w = a.shape
    x0 = x - (w / 2 if anchor == 'm' else (w if anchor == 'r' else 0))
    paint_img(cv.c, to_surface_rgba(rgb, a), x0, y - h / 2, alpha=alpha)
    if glow > 0:
        paint_img(cv.g, to_surface_rgba(rgb * glow, a), x0, y - h / 2, alpha=alpha)


def missing_glyphs(markup, weight=800, sans=False, font=None):
    """characters of a markup string that no font in the fallback chain can draw (they would show as tofu boxes)"""
    return sorted({ch for ch, _ in parse(markup, CREAM) if not ch.isspace()
                   and _font_choice(ch, 48, weight, sans, font) is None})


@functools.lru_cache(8192)
def glyph(ch, size, weight, sans, font=None):
    f = _font_for(ch, size, weight, sans, font)
    ref = _font(FONT_CJK_SANS if sans else FONT_CJK, size, weight)
    asc, desc = ref.getmetrics()
    adv = f.getlength(ch)
    pad = 4
    w = int(math.ceil(adv)) + 2 * pad + int(size * 0.2)
    hh = asc + desc + 2 * pad
    im = Image.new('L', (max(w, 1), hh), 0)
    d = ImageDraw.Draw(im)
    # vertically centre latin font on CJK metrics
    if f is not ref:
        fa, fd = f.getmetrics()
        yoff = (asc + desc - (fa + fd)) / 2 + (fa - fd) * 0.04
    else:
        yoff = 0
    d.text((pad, pad + yoff), ch, font=f, fill=255)
    return np.asarray(im, np.float32) / 255.0, adv, pad, hh


TAGS = {'h': HILITE, 'd': DIMC, 'w': CREAM}


def parse(markup, color):
    """[a]...[/]  colour spans"""
    out, cur, i = [], color, 0
    while i < len(markup):
        if markup[i] == '[':
            j = markup.index(']', i)
            tag = markup[i + 1:j]
            cur = color if tag == '/' else TAGS[tag]
            i = j + 1
            continue
        out.append((markup[i], cur))
        i += 1
    return out


def text_width(markup, size, weight=800, tracking=0.02, sans=False, font=None):
    chars = parse(markup, CREAM)
    return sum(glyph(c, int(size), weight, sans, font)[1] + tracking * size for c, _ in chars) - tracking * size


def add_text(cv, markup, x, y, size=56, color=None, alpha=1.0, t=1e9, anim='rise', anchor='m', weight=800,
             tracking=0.02, stagger=0.03, dur=0.5, shadow=0.85, glow=0.0, sans=False, scale=1.0, font=None):
    """queue text (drawn in post). t = time since appearance. anim: 'rise' (per-char), 'type', None.
    scale != 1 gives a 'stamp' slam-in when animated from ~1.35 -> 1.
    font = path to one font used for every glyph of this string (handwriting, kai, mono ...)."""
    color = color or CREAM
    if alpha <= 0.004 or t < 0:
        return
    cv.texts.append(dict(markup=markup, x=x, y=y, size=size, color=color, alpha=alpha, t=t, anim=anim,
                         anchor=anchor, weight=weight, tracking=tracking, stagger=stagger, dur=dur,
                         shadow=shadow, glow=glow, sans=sans, scale=scale, font=font))


def _render_text(img, d):
    size = int(d['size'])
    chars = parse(d['markup'], d['color'])
    if not chars:
        return
    gl = [glyph(c, size, d['weight'], d['sans'], d.get('font')) for c, _ in chars]
    adv = [g[1] + d['tracking'] * size for g in gl]
    total = sum(adv) - d['tracking'] * size
    hh = gl[0][3]
    padx = int(size * 0.9)
    bw, bh = int(total + 2 * padx + size), int(hh + 2 * padx)
    acc_a = np.zeros((bh, bw), np.float32)
    acc_c = np.zeros((bh, bw, 3), np.float32)
    cx = padx
    t = d['t']
    for i, ((ch, col), (m, a_, pad, _), av) in enumerate(zip(chars, gl, adv)):
        if d['anim'] == 'rise':
            k = ease_out((t - i * d['stagger']) / d['dur'])
            al = min(1.0, k * 1.5)
            dy = (1 - k) * size * 0.35
        elif d['anim'] == 'type':
            k = 1.0 if t * 18 > i else 0.0
            al, dy = k, 0
        else:
            al, dy = 1.0, 0
        if al > 0.01 and ch != ' ':
            x0 = int(round(cx - pad))
            y0 = int(round(padx + dy))
            h_, w_ = m.shape
            y1, x1 = min(bh, y0 + h_), min(bw, x0 + w_)
            mm = m[:y1 - y0, :x1 - x0] * al
            sub = acc_a[y0:y1, x0:x1]
            acc_c[y0:y1, x0:x1] = acc_c[y0:y1, x0:x1] * (1 - mm[..., None]) + np.array(col, np.float32) * mm[..., None]
            acc_a[y0:y1, x0:x1] = sub + mm * (1 - sub)
        cx += av
    sc = d['scale']
    if abs(sc - 1) > 1e-3:
        nw, nh = max(1, int(bw * sc)), max(1, int(bh * sc))
        acc_a = cv2.resize(acc_a, (nw, nh), interpolation=cv2.INTER_LINEAR)
        acc_c = cv2.resize(acc_c, (nw, nh), interpolation=cv2.INTER_LINEAR)
        bw, bh = nw, nh
        padx_s, total_s = padx * sc, total * sc
    else:
        padx_s, total_s = padx, total
    anc = d['anchor']
    left = d['x'] - (total_s / 2 if anc == 'm' else (total_s if anc == 'r' else 0)) - padx_s
    top = d['y'] - bh / 2
    X0, Y0 = int(round(left)), int(round(top))
    # clip to frame
    fx0, fy0 = max(0, X0), max(0, Y0)
    fx1, fy1 = min(W, X0 + bw), min(H, Y0 + bh)
    if fx1 <= fx0 or fy1 <= fy0:
        return
    sa = acc_a[fy0 - Y0:fy1 - Y0, fx0 - X0:fx1 - X0]
    scc = acc_c[fy0 - Y0:fy1 - Y0, fx0 - X0:fx1 - X0]
    region = img[fy0:fy1, fx0:fx1]
    A = d['alpha']
    if d['shadow'] > 0:
        sh = cv2.GaussianBlur(cv2.dilate(acc_a, np.ones((3, 3), np.uint8)), (0, 0), size * 0.22)
        sh = sh[fy0 - Y0:fy1 - Y0, fx0 - X0:fx1 - X0] * d['shadow'] * A
        region *= (1 - np.clip(sh * 1.3, 0, 0.92))[..., None]
    if d['glow'] > 0:
        gb = cv2.GaussianBlur(acc_c * acc_a[..., None], (0, 0), size * 0.3)[fy0 - Y0:fy1 - Y0, fx0 - X0:fx1 - X0]
        region += gb * d['glow'] * A
    m = (sa * A)[..., None]
    region[:] = region * (1 - m) + scc * m
    ys, xs = np.nonzero(m[..., 0] > 0.02)
    if len(ys):
        return (fx0 + int(xs.min()), fy0 + int(ys.min()), fx0 + int(xs.max()) + 1, fy0 + int(ys.max()) + 1)
    return None


def text_in_zones(cv, zones):
    """Call after finish(cv). zones = [(x0, y0, x1, y1)] as fractions of the frame (e.g. a cover's top-left corner
    (0, 0, 0.5, 0.25) that a platform badge will cover). Returns [(markup, box_px, zone)] for every text whose ink
    overlaps a zone - empty list means the zones are free of text (glow/shadow halos are not counted)."""
    hits = []
    for d, b in cv.text_boxes:
        for z in zones:
            zx0, zy0, zx1, zy1 = z[0] * W, z[1] * H, z[2] * W, z[3] * H
            if b[0] < zx1 and b[2] > zx0 and b[1] < zy1 and b[3] > zy0:
                hits.append((d['markup'], b, z))
    return hits


def group(cv, fn, a):
    """draw fn(cv) on both layers (base + glow) as one group and composite it with alpha a; texts queued by fn get
    their alpha scaled too. Use for whole-scene cross-fades / fading a sub-scene in over another without the
    double-exposure look of fading each element separately."""
    if a <= 0.003:
        return
    if a >= 0.997:
        fn(cv)
        return
    n0 = len(cv.texts)
    cv.c.push_group()
    cv.g.push_group()
    fn(cv)
    cv.g.pop_group_to_source()
    cv.g.paint_with_alpha(a)
    cv.c.pop_group_to_source()
    cv.c.paint_with_alpha(a)
    for d in cv.texts[n0:]:
        d['alpha'] *= a


# ---------------------------------------------------------------- post
_rng_grain = np.random.default_rng(99)
GRAIN = [(_rng_grain.standard_normal((H // 2, W // 2)).astype(np.float32)) for _ in range(12)]
_yy, _xx = np.mgrid[0:H, 0:W].astype(np.float32)
VIG = (1 - 0.55 * np.clip((((_xx - W / 2) / (W * 0.62)) ** 2 + ((_yy - H / 2) / (H * 0.70)) ** 2) - 0.25, 0, 1)
       ).astype(np.float32)[..., None]
del _yy, _xx


def surf_np(s, w, h):
    s.flush()
    a = np.ndarray((h, w, 4), np.uint8, s.get_data())
    return a[..., 2::-1].astype(np.float32) / 255.0


def finish(cv, frame_idx=0):
    img = surf_np(cv.base, W, H)
    gl = surf_np(cv.glow, W // 2, H // 2)
    # bloom of emission layer
    if gl.max() > 0.002:
        b = gl * 0.55 + cv2.GaussianBlur(gl, (0, 0), 4) * 0.7 + cv2.GaussianBlur(gl, (0, 0), 14) * 0.6
        b2 = cv2.resize(cv2.GaussianBlur(cv2.resize(gl, (W // 8, H // 8), interpolation=cv2.INTER_AREA), (0, 0), 6),
                        (W // 2, H // 2), interpolation=cv2.INTER_LINEAR)
        b = b + b2 * 0.7
        img += cv2.resize(b, (W, H), interpolation=cv2.INTER_LINEAR)
    cv.text_boxes = []
    for d in cv.texts:
        b = _render_text(img, d)
        if b:
            cv.text_boxes.append((d, b))
    if cv.flash > 0:
        img += np.array([1.0, 0.85, 0.6], np.float32) * cv.flash
    # tone: soft shoulder
    img = img / (1 + np.maximum(img - 0.85, 0) * 1.2)
    if cv.ca > 0:
        sft = int(cv.ca)
        img[..., 0] = np.roll(img[..., 0], sft, 1)
        img[..., 2] = np.roll(img[..., 2], -sft, 1)
    img *= VIG if cv.vignette >= 1 else (1 - (1 - VIG) * cv.vignette)
    gr = cv2.resize(GRAIN[frame_idx % len(GRAIN)], (W, H), interpolation=cv2.INTER_LINEAR)
    img += gr[..., None] * (0.022 * cv.grain) * (0.4 + img)
    img *= cv.fade
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)
