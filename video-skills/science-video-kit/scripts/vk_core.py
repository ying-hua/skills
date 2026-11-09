"""vk_core - style-neutral 2D drawing core for procedural science videos (cairo + cv2 + PIL).

  Canvas      cairo base surface + half-res EMISSION surface (cv.g, additive) that gets bloomed in finish()
  helpers     easing (ss, ease_out, ease_io, back_out), win() visibility windows, hrand() deterministic hash, fbm noise,
              pnoise (fbm that tiles in x for equirect textures),
  3D          Cam (look-at pinhole: proj points, per-pixel rays), ortho_project / ortho_lonlat / sample_equirect (globes)
              splat_points (thousands of sub-pixel point lights into a numpy image)
  effects     tracer (glowing streak), muzzle (star flash + smoke), impact (dust burst + shock ring), dust_motes,
              reticle, dashed_line, arrow_head, polyline (partial stroke-on), rrect, panel
  text        add_text(cv, '[a]colored[/] markup', ...) queued and rasterised in finish(); CJK + latin font mixing;
              cv.text_boxes / text_in_zones() report where text ink landed (cover safe-zone checks)
  compose     group(cv, fn, a): draw a sub-scene on both layers and fade it as one piece
  2.5D        tilt_homography + warp_layer(cv, draw, lw, lh, Hm): a flat scene laid on a tilted table (both layers)
  world text  world_text(ctx, ...): cairo toy-font latin labels that follow camera transforms and warps
  post        finish(cv, idx) -> uint8 HxWx3: bloom, text, flash, soft shoulder (cv.shoulder), chromatic aberration, vignette, grain

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
    """works on scalars and numpy arrays"""
    if isinstance(x, np.ndarray):
        return np.clip(x, 0.0, 1.0)
    return min(1.0, max(0.0, x))


def ss(a, b, x):
    """smoothstep from a to b; x may be a scalar or a numpy array"""
    if b == a:
        return (np.asarray(x) >= a).astype(np.float64) if isinstance(x, np.ndarray) else float(x >= a)
    t = clamp01((x - a) / (b - a))
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
        self.shoulder = 1.2       # highlight roll-off above 0.85: output tops out near 1/shoulder (1.2 -> ~0.83 grey);
        #                           lower it (e.g. 0.15) when a big area must read as true white (blazing sky, flash)
        self.text_boxes = []      # [(text dict, ink box (x0, y0, x1, y1) px)] filled by finish()
        self.math_boxes = []      # [(tex, ink box px)] filled by add_math (drawn immediately)

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


def _unit(img):
    """uint8 images are 0..255: scale them to 0..1 (multiplying a uint8 array by 255 saturates it to white)"""
    return img.astype(np.float32) / 255.0 if img.dtype == np.uint8 else img


def to_surface(img, persist=False):
    """rgb (h,w,3) float 0..1 or uint8 0..255 -> cairo RGB24 surface. The numpy buffer is kept alive in _KEEP
    (per-frame, clear it after finish) or, with persist=True, in _PERSIST (for textures cached at import time and
    reused every frame)."""
    img = _unit(img)
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
    img, alpha = _unit(img), _unit(np.asarray(alpha))
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


def splat_points(img, xs, ys, flux, col=(1.0, 1.0, 1.0), sigma=0.8):
    """add many point lights (stars, sparks, particles) to a float HxWx3 image in place: sub-pixel bilinear deposit
    (no 1 px jitter when they drift slowly) then a Gaussian blur of `sigma` px for a round core. flux: scalar or
    per-point array. Thousands of points cost about one blur - far cheaper than one cairo arc each."""
    h, w = img.shape[:2]
    xs, ys = np.asarray(xs, np.float64), np.asarray(ys, np.float64)
    f = np.broadcast_to(np.asarray(flux, np.float32), xs.shape)
    x0, y0 = np.floor(xs).astype(int), np.floor(ys).astype(int)
    ok = (x0 >= 0) & (y0 >= 0) & (x0 < w - 1) & (y0 < h - 1)
    x0, y0, f = x0[ok], y0[ok], f[ok]
    fx, fy = (xs[ok] - x0).astype(np.float32), (ys[ok] - y0).astype(np.float32)
    # np.bincount on flat indices: same sums as np.add.at, roughly 10x faster for 1e5+ points
    base = y0.astype(np.int64) * w + x0
    acc = np.bincount(base, f * (1 - fx) * (1 - fy), h * w)
    acc += np.bincount(base + 1, f * fx * (1 - fy), h * w)
    acc += np.bincount(base + w, f * (1 - fx) * fy, h * w)
    acc += np.bincount(base + w + 1, f * fx * fy, h * w)
    acc = acc.reshape(h, w).astype(np.float32)
    if sigma > 0:
        acc = cv2.GaussianBlur(acc, (0, 0), sigma)
    img += acc[..., None] * np.asarray(col, np.float32)
    return img


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


def pnoise(h, w, seed=0, octaves=5, base=4, persist=0.55):
    """fbm that tiles in x (left edge continues the right edge), normalised to 0..1. Use it for equirect (lon x lat)
    textures wrapped on a sphere - plain fbm leaves a visible seam at lon = +-180. Detail still pinches toward the
    poles of a sphere; fade it out above ~75 deg latitude."""
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        gw = base * 2 ** o
        gh = max(2, int(round(gw * h / w)))
        g = rng.random((gh + 3, gw + 3)).astype(np.float32)
        g[:, -3:] = g[:, :3]
        big = cv2.resize(g, (int(w * (gw + 3) / gw), int(h * (gh + 3) / gh)), interpolation=cv2.INTER_CUBIC)
        ox, oy = int(w / gw), int(h / gh)
        out += amp * big[oy:oy + h, ox:ox + w]
        tot += amp
        amp *= persist
    out -= out.min()
    return out / max(1e-6, out.max())


def equal_earth(lon, lat):
    """Equal Earth world projection (Savric et al. 2018): degrees -> projected units, x right / y up,
    x in about +-2.7064 and y in +-1.3173. Equal-area and good-looking for world maps; scale with px = x * k."""
    A1, A2, A3, A4 = 1.340264, -0.081106, 0.000893, 0.003796
    lon = np.radians(np.asarray(lon, float))
    th = np.arcsin(math.sqrt(3) / 2 * np.sin(np.radians(np.asarray(lat, float))))
    t2 = th * th
    t6 = t2 * t2 * t2
    x = 2 * math.sqrt(3) * lon * np.cos(th) / (3 * (9 * A4 * t6 * t2 + 7 * A3 * t6 + 3 * A2 * t2 + A1))
    return x, th * (A1 + A2 * t2 + t6 * (A3 + A4 * t2))


def lattice_dots(w, h, x0, y0, k, spacing, px=(6.0, 12.0), sigma=1.25):
    """(h, w) float32 halftone dots pinned to world coordinates: the screen shows world point (x0, y0) at its centre,
    k = screen px per world unit, `spacing` = lattice step (world units) at the coarsest level. As the camera zooms,
    the lattice halves and the finer level crossfades in, so dots stay px[0]..px[1] apart and a constant size on screen
    (an "LED map" / dotted land that survives a 10x zoom). Gaussian dots are separable -> one np.outer per level;
    multiply by a land mask for a dotted map."""
    sp = spacing * k
    lv = math.log2(max(sp, 1e-9) / px[0]) / math.log2(px[1] / px[0])
    n = math.floor(lv)
    fr = lv - n
    d0 = spacing / (px[1] / px[0]) ** n

    def prof(m, c0, d):
        u = (np.arange(m) - m / 2) / k + c0
        f = (u / d) % 1.0
        dist = np.minimum(f, 1 - f) * d * k
        return np.exp(-dist * dist / (2 * sigma * sigma)).astype(np.float32)

    out = np.zeros((h, w), np.float32)
    for d, wgt in ((d0, 1 - fr), (d0 / (px[1] / px[0]), fr)):
        if wgt > 0.01:
            out += np.outer(prof(h, y0, d), prof(w, x0, d)) * wgt
    return out


def worley(h, w, spacing, seed=0, jitter=0.9, tile=True, labels=False):
    """cellular (Worley) noise: distance to the nearest of ~(h/spacing)*(w/spacing) jittered seeds, divided by
    `spacing` (0 at a seed, ~0.5-0.7 on cell borders). 1 - d gives bright cells with dark lanes (solar granulation,
    plant cells, foam, scales); edges of `labels` give cell walls. tile=True puts the seeds on a torus so the texture
    repeats seamlessly (EXTEND_REPEAT, cv2.BORDER_WRAP, scrolling ground planes) - a plain distance transform leaves a
    hard seam where the texture wraps. labels=True also returns the per-pixel id of the nearest seed."""
    rng = np.random.default_rng(seed)
    ny, nx = max(1, int(round(h / spacing))), max(1, int(round(w / spacing)))
    m = np.full((h, w), 255, np.uint8)
    for i in range(ny):
        for j in range(nx):
            y = int((i + 0.5 + rng.uniform(-jitter, jitter) / 2) * h / ny) % h
            x = int((j + 0.5 + rng.uniform(-jitter, jitter) / 2) * w / nx) % w
            m[y, x] = 0
    src = np.tile(m, (3, 3)) if tile else m
    d, lab = cv2.distanceTransformWithLabels(src, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    # every seed pixel has its own label; map labels to one id per seed (the 9 tiled copies share it)
    ys, xs = np.nonzero(src == 0)
    ids = np.zeros(int(lab.max()) + 1, np.int64)
    ids[lab[ys, xs]] = (ys % h) * w + (xs % w)
    lab = ids[lab]
    if tile:
        d, lab = d[h:2 * h, w:2 * w], lab[h:2 * h, w:2 * w]
    d = (d / spacing).astype(np.float32)
    return (d, lab) if labels else d


# ---------------------------------------------------------------- 3D pinhole camera (cairo / numpy scenes)
class Cam:
    """look-at pinhole camera for drawing 3D scenes with cairo/numpy (y up). proj() maps points to screen pixels,
    rays() gives per-pixel view directions for ray casting backgrounds (e.g. the inside of a sphere) on a grid of any
    size (render at half res and upscale)."""

    def __init__(self, pos, target, fov=60.0, roll=0.0, w=None, h=None):
        self.p = np.asarray(pos, np.float64)
        f = np.asarray(target, np.float64) - self.p
        f /= np.linalg.norm(f)
        r = np.cross(f, [0.0, 1.0, 0.0])
        if np.linalg.norm(r) < 1e-6:          # looking straight up/down: pick any right vector
            r = np.array([1.0, 0.0, 0.0])
        r /= np.linalg.norm(r)
        u = np.cross(r, f)
        if roll:
            cr, sr = math.cos(roll), math.sin(roll)
            r, u = r * cr + u * sr, -r * sr + u * cr
        self.r, self.u, self.f = r, u, f
        self.w, self.h = w or W, h or H
        self.foc = (self.w / 2) / math.tan(math.radians(fov) / 2)     # horizontal fov in degrees

    def proj(self, P):
        """P (..., 3) -> (sx, sy, depth); depth <= 0 means behind the camera (cull those)"""
        d = np.asarray(P, np.float64) - self.p
        x, y, z = d @ self.r, d @ self.u, d @ self.f
        zz = np.where(z > 1e-3, z, 1e-3)
        return self.w / 2 + self.foc * x / zz, self.h / 2 - self.foc * y / zz, z

    def rays(self, w, h):
        """unit view directions (h, w, 3) float32 for a w x h pixel grid covering the frame"""
        foc = self.foc * w / self.w
        X, Y = np.meshgrid((np.arange(w, dtype=np.float32) + 0.5 - w / 2) / foc,
                           -(np.arange(h, dtype=np.float32) + 0.5 - h / 2) / foc)
        d = X[..., None] * self.r.astype(np.float32) + Y[..., None] * self.u.astype(np.float32) +             self.f.astype(np.float32)
        return d / np.linalg.norm(d, axis=-1, keepdims=True)


# ---------------------------------------------------------------- orthographic globe from an equirect texture
def ortho_project(lon, lat, lon0, lat0):
    """(deg) -> unit-disc x (east), y (north, up), z (> 0 on the visible hemisphere) for a globe centred on
    (lon0, lat0). Screen point: (cx + x * r, cy - y * r)."""
    lam = np.radians(np.asarray(lon, np.float64) - lon0)
    ph = np.radians(np.asarray(lat, np.float64))
    X, Y, Z = np.cos(ph) * np.cos(lam), np.cos(ph) * np.sin(lam), np.sin(ph)
    cl, sl = math.cos(math.radians(lat0)), math.sin(math.radians(lat0))
    return Y, -X * sl + Z * cl, X * cl + Z * sl


def ortho_lonlat(cx, cy, r, lon0, lat0, box=None, step=1):
    """inverse of ortho_project for every screen pixel in box=(x0, y0, x1, y1) (default: the disc's bounding box
    clipped to the frame). Returns lon, lat (deg), inside-disc mask, z (1 at the centre, 0 at the limb) and the
    box used - feed lon/lat to sample_equirect() and shade with z."""
    if box is None:
        box = (max(0, int(cx - r - 2)), max(0, int(cy - r - 2)), min(W, int(cx + r + 2)), min(H, int(cy + r + 2)))
    x0, y0, x1, y1 = box
    X, Y = np.meshgrid(np.arange(x0, x1, step, dtype=np.float32) + 0.5, np.arange(y0, y1, step, dtype=np.float32) + 0.5)
    nx, ny = (X - cx) / r, -(Y - cy) / r
    rr = nx * nx + ny * ny
    z = np.sqrt(np.clip(1 - rr, 0, 1))
    cl, sl = math.cos(math.radians(lat0)), math.sin(math.radians(lat0))
    lon = (np.degrees(np.arctan2(nx, z * cl - ny * sl)) + lon0 + 180) % 360 - 180
    lat = np.degrees(np.arcsin(np.clip(z * sl + ny * cl, -1, 1)))
    return lon, lat, rr < 1, z, box


def sample_equirect(tex, lon, lat):
    """bilinear lookup of an equirect texture (rows = 90..-90 lat, cols = -180..180 lon) that wraps in longitude"""
    th, tw = tex.shape[:2]
    mx = ((np.asarray(lon) + 180) / 360 * tw - 0.5).astype(np.float32)
    my = ((90 - np.asarray(lat)) / 180 * th - 0.5).astype(np.float32)
    return cv2.remap(tex, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)


def sample_points(img, mx, my, interp=cv2.INTER_LINEAR, border=cv2.BORDER_WRAP):
    """cv2.remap for an arbitrary number of sample points (1-D pixel coords mx, my of any length). cv2.remap needs
    both map dimensions < 32767, so a (N, 1) map with N > 32767 fails; the points are folded into rows of 2048.
    Typical use: sample only the pixels of a disc / a selection (globe pixels, per-plate caps) from a big texture."""
    mx = np.asarray(mx, np.float32).ravel()
    my = np.asarray(my, np.float32).ravel()
    n = mx.size
    if n == 0:
        return np.zeros((0,) + img.shape[2:], img.dtype)
    cw = 2048
    rows = (n + cw - 1) // cw
    pad = rows * cw - n
    MX = np.concatenate([mx, np.zeros(pad, np.float32)]).reshape(rows, cw)
    MY = np.concatenate([my, np.zeros(pad, np.float32)]).reshape(rows, cw)
    out = cv2.remap(img, MX, MY, interp, borderMode=border)
    return out.reshape((rows * cw,) + img.shape[2:])[:n]


def _unit3(lon, lat):
    lo, la = np.radians(np.asarray(lon, np.float64)), np.radians(np.asarray(lat, np.float64))
    return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], -1)


def fit_rotation(src, dst):
    """best rotation (3x3, least squares / Kabsch) taking lon/lat points src [(lon, lat), ...] onto dst - e.g. fit a
    continent's coastline points onto where they sat in an old supercontinent, or rotate a region of a globe so
    chosen landmarks land on chosen spots. Use rotate_lonlat(M, ..., k) to animate it."""
    a, b = _unit3(*np.array(src, np.float64).T), _unit3(*np.array(dst, np.float64).T)
    U, _, Vt = np.linalg.svd(a.T @ b)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    return Vt.T @ np.diag([1.0, 1.0, d]) @ U.T


def rot_power(M, k):
    """fraction k of rotation M (same axis, k * angle): k = 0 -> identity, 1 -> M. Linear in angle = constant speed
    along great circles (slerp from the identity)."""
    ang = math.acos(max(-1.0, min(1.0, (np.trace(M) - 1) / 2)))
    if ang < 1e-9:
        return np.eye(3)
    ax = np.array([M[2, 1] - M[1, 2], M[0, 2] - M[2, 0], M[1, 0] - M[0, 1]]) / (2 * math.sin(ang))
    K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
    th = ang * k
    return np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * (K @ K)


def rotate_lonlat(M, lon, lat, k=1.0):
    """apply rotation M (or the fraction k of it) to lon/lat (deg). Returns lon, lat. For per-pixel drawing of a
    rotated region use the inverse: sample the texture at rotate_lonlat(M.T, screen_lon, screen_lat)."""
    R = M if k == 1.0 else rot_power(M, k)
    v = _unit3(lon, lat) @ R.T
    return np.degrees(np.arctan2(v[..., 1], v[..., 0])), np.degrees(np.arcsin(np.clip(v[..., 2], -1, 1)))


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


def polyline(ctx, pts, close=True, frac=1.0):
    """add a polyline path (call stroke()/fill() yourself). frac < 1 traces only that share of the total length - a
    'drawn on' outline (stick in sand, brush, pen). Starts with new_path(): after show_text() cairo keeps a current
    point, and the first segment would otherwise be joined to it."""
    ctx.new_path()
    if len(pts) < 2 or frac <= 0:
        return
    P = list(pts) + ([pts[0]] if close else [])
    if frac >= 1:
        ctx.move_to(*P[0])
        for p in P[1:-1] if close else P[1:]:
            ctx.line_to(*p)
        if close:
            ctx.close_path()
        return
    segs = [math.dist(P[i], P[i + 1]) for i in range(len(P) - 1)]
    L = sum(segs) * frac
    ctx.move_to(*P[0])
    for i, s in enumerate(segs):
        if L <= 0:
            break
        u = min(1.0, L / s) if s > 0 else 1.0
        ctx.line_to(P[i][0] + (P[i + 1][0] - P[i][0]) * u, P[i][1] + (P[i + 1][1] - P[i][1]) * u)
        L -= s


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


_MATH_CACHE = {}     # (tex, size, colour, fontset) -> (surface, glow surface, w, h, ink box); kept for the process


def add_math(cv, tex, x, y, size=48, color=None, alpha=1.0, anchor='m', glow=0.0, fontset='stix'):
    """paint a formula with real sub/superscripts, fractions and roots onto the base layer, centred at (x, y)
    (anchor 'l'/'r' align left/right edge). Drawn immediately (not in finish), so call it in draw order.
    The rendered formula is cached per (tex, size, colour, fontset): mathtext costs ~50-150 ms, so per-frame calls
    would dominate a render. The ink box goes to cv.math_boxes so text_in_zones() sees formulas too."""
    if alpha <= 0.004:
        return
    key = (tex, int(size), tuple(round(float(c), 4) for c in (color or CREAM)), fontset)
    if key not in _MATH_CACHE:
        rgb, a = math_img(tex, int(size), key[2], fontset)
        ys, xs = np.nonzero(a > 0.25)
        ink = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1) if len(xs) else (0, 0, 0, 0)
        _MATH_CACHE[key] = (to_surface_rgba(rgb, a, persist=True), to_surface_rgba(rgb * 0.6, a, persist=True),
                            a.shape[1], a.shape[0], ink)
    s1, s2, w, h, ink = _MATH_CACHE[key]
    x0 = x - (w / 2 if anchor == 'm' else (w if anchor == 'r' else 0))
    paint_img(cv.c, s1, x0, y - h / 2, alpha=alpha)
    if glow > 0:
        paint_img(cv.g, s2, x0, y - h / 2, alpha=min(1.0, alpha * glow / 0.6))
    cv.math_boxes.append((tex, (x0 + ink[0], y - h / 2 + ink[1], x0 + ink[2], y - h / 2 + ink[3])))


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
             tracking=0.02, stagger=0.03, dur=0.5, shadow=0.85, glow=0.0, sans=False, scale=1.0, font=None, late=False):
    """queue text (drawn in post). t = time since appearance. anim: 'rise' (per-char), 'type', None.
    scale != 1 gives a 'stamp' slam-in when animated from ~1.35 -> 1.
    font = path to one font used for every glyph of this string (handwriting, kai, mono ...).
    late=True: finish() leaves this text out (kept in cv.late_texts) so it can be drawn with draw_texts() AFTER a
    full-frame effect (blur, eyelids, squash ...) and stay sharp on top of it."""
    color = color or CREAM
    if alpha <= 0.004 or t < 0:
        return
    cv.texts.append(dict(markup=markup, x=x, y=y, size=size, color=color, alpha=alpha, t=t, anim=anim,
                         anchor=anchor, weight=weight, tracking=tracking, stagger=stagger, dur=dur,
                         shadow=shadow, glow=glow, sans=sans, scale=scale, font=font, late=late))


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


def draw_texts(img, texts):
    """composite queued text dicts (e.g. cv.late_texts) onto a finished uint8 RGB frame; returns (frame, ink boxes).
    Use after a whole-frame effect in Section.post so captions are not blurred / darkened with the picture."""
    f = img.astype(np.float32) / 255.0
    boxes = [(d, _render_text(f, d)) for d in texts]
    return (np.clip(f, 0, 1) * 255 + 0.5).astype(np.uint8), [(d, b) for d, b in boxes if b]


def text_in_zones(cv, zones):
    """Call after finish(cv). zones = [(x0, y0, x1, y1)] as fractions of the frame (e.g. a cover's top-left corner
    (0, 0, 0.5, 0.25) that a platform badge will cover). Returns [(markup, box_px, zone)] for every text whose ink
    overlaps a zone - empty list means the zones are free of text (glow/shadow halos are not counted).
    Formulas painted with add_math are checked too (their markup is the tex string)."""
    hits = []
    items = [(d['markup'], b) for d, b in cv.text_boxes] + list(getattr(cv, 'math_boxes', []))
    for m, b in items:
        for z in zones:
            zx0, zy0, zx1, zy1 = z[0] * W, z[1] * H, z[2] * W, z[3] * H
            if b[0] < zx1 and b[2] > zx0 and b[1] < zy1 and b[3] > zy0:
                hits.append((m, b, z))
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


def world_text(ctx, s, x, y, size, col, alpha=1.0, face='Consolas', bold=True, anchor='m', italic=False):
    """draw latin text straight onto a cairo context (cairo toy font by family name, e.g. 'Consolas', 'Georgia').
    Unlike add_text it follows set_cam / ctx transforms and perspective-warped layers, and is cheap enough for
    hundreds of labels per frame (dials, tables, ciphertext). y = vertical centre of capitals. No CJK shaping:
    keep Chinese in add_text. Ends with new_path() so the next arc() is not joined to the text."""
    if alpha <= 0.003:
        return
    ctx.select_font_face(face, cairo.FONT_SLANT_ITALIC if italic else cairo.FONT_SLANT_NORMAL,
                         cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(size)
    adv = ctx.text_extents(s).x_advance
    x0 = x - adv / 2 if anchor == 'm' else (x - adv if anchor == 'r' else x)
    ctx.move_to(x0, y + size * 0.36)
    ctx.set_source_rgba(*col, alpha)
    ctx.show_text(s)
    ctx.new_path()


def tilt_homography(lw, lh, zoom=1.0, tilt=0.5, cx=None, cy=None, roll=0.0, sx=None, sy=None, scale=1.0, D=2200.0):
    """3x3 homography that lays a flat layer (lw x lh layer px, drawn at `scale` px per unit) on a table tilted back
    by `tilt` radians (far edge = top), seen by a pinhole camera: layer point (cx, cy) (units) lands on screen (sx, sy),
    zoom ~ screen px per unit at that point, roll rotates the shot. Use with warp_layer."""
    cx = lw / 2 if cx is None else cx
    cy = lh / 2 if cy is None else cy
    sx = W / 2 if sx is None else sx
    sy = H / 2 if sy is None else sy
    f = D * zoom
    ca, sa, cr, sr = math.cos(tilt), math.sin(tilt), math.cos(roll), math.sin(roll)

    def proj(u, v):
        X, Y = u - cx, v - cy
        z = D - Y * sa
        px, py = f * X / z, f * Y * ca / z
        return sx + px * cr - py * sr, sy + px * sr + py * cr

    src = np.float32([[0, 0], [lw * scale, 0], [lw * scale, lh * scale], [0, lh * scale]])
    dst = np.float32([proj(0, 0), proj(lw, 0), proj(lw, lh), proj(0, lh)])
    return cv2.getPerspectiveTransform(src, dst)


def _paint_warped(ctx, arr, Hm, ow, oh, alpha):
    out = np.ascontiguousarray(cv2.warpPerspective(arr, Hm, (ow, oh), flags=cv2.INTER_LINEAR))
    _KEEP.append(out)
    s = cairo.ImageSurface.create_for_data(memoryview(out), cairo.FORMAT_ARGB32, ow, oh)
    ctx.save()
    ctx.identity_matrix()
    ctx.set_source_surface(s, 0, 0)
    ctx.paint_with_alpha(alpha)
    ctx.restore()


def warp_point(Hm, x, y, scale=1.0):
    """screen px of a layer point (x, y) in layer units - for add_text labels, glows or hit markers that must sit on a
    warped layer. Pass the same `scale` that went to tilt_homography / warp_layer."""
    p = np.asarray(Hm, np.float64) @ np.array([x * scale, y * scale, 1.0])
    return float(p[0] / p[2]), float(p[1] / p[2])


def warp_layer(cv, draw, lw, lh, Hm, alpha=1.0, scale=1.0):
    """perspective 2.5D: draw(c, g) paints a flat scene (a machine, a board, a map) in layer units 0..lw x 0..lh on a
    transparent base context c and a half-res additive glow context g; both are warped by Hm (tilt_homography) onto
    cv.c and cv.g, so lamps on the tilted object still bloom. scale = layer px per unit (raise it for close-ups so
    the texture is not magnified; ~0.05 s per 2000 px layer). Clear _KEEP per frame as usual.
    Hm must come from tilt_homography(..., scale=<the same scale>) - with a mismatch the layer lands shrunk in a corner."""
    w, h = int(lw * scale), int(lh * scale)
    sb = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    sg = cairo.ImageSurface(cairo.FORMAT_ARGB32, w // 2, h // 2)
    c, g = cairo.Context(sb), cairo.Context(sg)
    c.scale(scale, scale)
    g.scale(scale / 2, scale / 2)
    for x in (c, g):
        x.set_line_cap(cairo.LINE_CAP_ROUND)
        x.set_line_join(cairo.LINE_JOIN_ROUND)
    g.set_operator(cairo.OPERATOR_ADD)
    draw(c, g)
    for s_ in (sb, sg):
        s_.flush()
    _paint_warped(cv.c, np.ndarray((h, w, 4), np.uint8, sb.get_data()), Hm, W, H, alpha)
    H2 = np.diag([0.5, 0.5, 1.0]) @ Hm @ np.diag([2.0, 2.0, 1.0])
    _paint_warped(cv.g, np.ndarray((h // 2, w // 2, 4), np.uint8, sg.get_data()), H2, W // 2, H // 2, alpha)


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
    cv.late_texts = [d for d in cv.texts if d.get('late')]
    for d in cv.texts:
        if d.get('late'):
            continue
        b = _render_text(img, d)
        if b:
            cv.text_boxes.append((d, b))
    if cv.flash > 0:
        img += np.array([1.0, 0.85, 0.6], np.float32) * cv.flash
    # tone: soft shoulder
    img = img / (1 + np.maximum(img - 0.85, 0) * cv.shoulder)
    if cv.ca > 0:
        sft = int(cv.ca)
        img[..., 0] = np.roll(img[..., 0], sft, 1)
        img[..., 2] = np.roll(img[..., 2], -sft, 1)
    img *= VIG if cv.vignette >= 1 else (1 - (1 - VIG) * cv.vignette)
    gr = cv2.resize(GRAIN[frame_idx % len(GRAIN)], (W, H), interpolation=cv2.INTER_LINEAR)
    img += gr[..., None] * (0.022 * cv.grain) * (0.4 + img)
    img *= cv.fade
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)
