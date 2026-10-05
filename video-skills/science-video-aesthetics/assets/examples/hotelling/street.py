"""Front-view shopping street (hook + real-world section), voters spectrum, converging phones."""
import math
import random
from gfx import *

GROUND = 850
rng = random.Random(11)

# (x, w, kind, sign, wall)
SHOPS = [
    (-400, 400, 'rent', '旺铺招租', hexc('#D9D4CC')),
    (0, 380, 'rent', '旺铺招租', hexc('#D6D0C6')),
    (380, 320, 'plain', '洗衣店', hexc('#BFD9EA')),
    (700, 260, 'tea', '草莓奶茶', hexc('#F8D3CC')),
    (960, 260, 'tea2', '薄荷奶茶', hexc('#CDEDE1')),
    (1220, 320, 'plain', '花店', hexc('#F4E3B5')),
    (1540, 380, 'rent', '旺铺招租', hexc('#D9D4CC')),
    (1920, 360, 'rent', '旺铺招租', hexc('#D6D0C6')),
    (2280, 270, 'burger', '汉堡', hexc('#FBE0B0')),
    (2550, 270, 'chicken', '炸鸡', hexc('#F7CDB8')),
    (2820, 380, 'rent', '旺铺招租', hexc('#D9D4CC')),
    (3200, 270, 'gas', '加油站', hexc('#D3E2F3')),
    (3470, 270, 'gas2', '加油站', hexc('#E2D7F2')),
    (3740, 400, 'rent', '旺铺招租', hexc('#D6D0C6')),
    (4140, 400, 'rent', '旺铺招租', hexc('#D9D4CC')),
]
HEIGHTS = [rng.uniform(470, 640) for _ in SHOPS]
CLOUDS = [(rng.uniform(-300, 4500), rng.uniform(70, 260), rng.uniform(0.7, 1.4)) for _ in range(14)]
SHIRTS = [CORAL, MINT, BUTTER, hexc('#6FA8DC'), PINK, hexc('#9B8FD6'), hexc('#F49E4C'), NAVY]
SKIN = [hexc('#F5CBA7'), hexc('#E0A97E'), hexc('#C68863'), hexc('#8D5B3E')]
HAIR = [hexc('#3B2A20'), hexc('#6B4226'), hexc('#1E1B1A'), hexc('#C99A5B')]


def awning(ctx, x, y, w, h, c1, c2):
    n = max(4, int(w / 34))
    sw = w / n
    for i in range(n):
        ctx.move_to(x + i * sw, y)
        ctx.line_to(x + (i + 1) * sw, y)
        ctx.line_to(x + (i + 1) * sw, y + h)
        ctx.arc(x + (i + .5) * sw, y + h, sw / 2, 0, math.pi)
        ctx.close_path()
        fill(ctx, c1 if i % 2 == 0 else c2)
    ctx.rectangle(x - 6, y - 6, w + 12, 10)
    fill(ctx, NAVY, 0.85)


def person_side(ctx, x, y, s, shirt, skin, hair, t, ph, cup=None, face=1):
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(s * face, s)
    b = 1.5 * math.sin(t * 3 + ph)
    rrect(ctx, -9, -44, 8, 44, 4)
    fill(ctx, NAVY)
    rrect(ctx, 1, -44, 8, 44, 4)
    fill(ctx, NAVY)
    rrect(ctx, -14, -92 + b, 28, 52, 12)
    fill(ctx, shirt)
    circle(ctx, 0, -106 + b, 14)
    fill(ctx, skin)
    ctx.arc(0, -108 + b, 14.5, math.pi * 0.95, math.pi * 2.05)
    fill(ctx, hair)
    circle(ctx, 8, -106 + b, 1.8)
    fill(ctx, NAVY)
    if cup is not None:
        rrect(ctx, 10, -76 + b, 14, 20, 3)
        fill(ctx, cup)
        ctx.move_to(19, -76 + b)
        ctx.line_to(23, -88 + b)
        ctx.set_line_width(2.5)
        src(ctx, NAVY)
        ctx.stroke()
    ctx.restore()


def draw_shop(ctx, x, w, kind, sign, wall, hb, t):
    top = GROUND - hb
    ctx.rectangle(x, top, w, hb)
    fill(ctx, wall)
    # cornice
    ctx.rectangle(x - 4, top - 12, w + 8, 16)
    fill(ctx, lerpc(wall, NAVY, 0.25))
    # upper windows
    rows = int((hb - 330) / 110)
    cols = max(2, int(w / 110))
    for r in range(rows):
        for c in range(cols):
            wx = x + (c + .5) * w / cols - 26
            wy = top + 40 + r * 110
            rrect(ctx, wx, wy, 52, 66, 26 if (kind in ('tea', 'tea2') and r == 0) else 4)
            fill(ctx, hexc('#7FB7CF'))
            ctx.rectangle(wx + 6, wy + 6, 16, 54)
            fill(ctx, CREAM, 0.35)
            ctx.rectangle(wx - 5, wy + 64, 62, 8)
            fill(ctx, lerpc(wall, NAVY, 0.3))
    # shop front
    fy = GROUND - 250
    rent = kind == 'rent'
    ctx.rectangle(x + 14, fy + 60, w - 28, 190)
    fill(ctx, hexc('#3B4A63') if not rent else hexc('#9A9A9A'))
    ctx.rectangle(x + 22, fy + 68, w - 44, 120)
    fill(ctx, hexc('#FFE7B8') if not rent else hexc('#C9C6C0'))
    if rent:
        ctx.rectangle(x + 22, fy + 68, w - 44, 182)
        fill(ctx, hexc('#B9B5AE'))
        for k in range(3):
            ctx.move_to(x + 30 + k * 60, fy + 75)
            ctx.line_to(x + 90 + k * 60, fy + 240)
        ctx.set_line_width(3)
        src(ctx, CREAM, 0.35)
        ctx.stroke()
        rrect(ctx, x + w / 2 - 70, fy + 110, 140, 70, 6)
        fill(ctx, CREAM)
        text(ctx, '旺铺', x + w / 2, fy + 130, 26, F_BODY, RED)
        text(ctx, '招租', x + w / 2, fy + 162, 26, F_BODY, RED)
        return
    # door
    ctx.rectangle(x + w - 84, fy + 100, 56, 150)
    fill(ctx, hexc('#2B3A55'))
    ctx.rectangle(x + w - 78, fy + 108, 44, 80)
    fill(ctx, hexc('#9FD3E6'), 0.7)
    cols = {'tea': (CORAL, CREAM), 'tea2': (MINT, CREAM), 'burger': (BUTTER, CORAL), 'chicken': (hexc('#F49E4C'), CREAM),
            'plain': (hexc('#6FA8DC'), CREAM), 'gas': (hexc('#6FA8DC'), CREAM), 'gas2': (hexc('#9B8FD6'), CREAM)}[kind]
    # goods in window
    for k in range(4):
        gx = x + 40 + k * 34
        if gx > x + w - 110:
            break
        if kind in ('tea', 'tea2'):
            rrect(ctx, gx, fy + 130, 22, 34, 4)
            fill(ctx, cols[0])
            ctx.rectangle(gx, fy + 130, 22, 8)
            fill(ctx, CREAM)
            for b in range(3):
                circle(ctx, gx + 5 + b * 6, fy + 158, 2.5)
                fill(ctx, NAVY)
        else:
            circle(ctx, gx + 11, fy + 150, 12)
            fill(ctx, cols[0])
    awning(ctx, x + 6, fy, w - 12, 46, *cols)
    # sign board
    rrect(ctx, x + w / 2 - 105, fy - 86, 210, 64, 14)
    fill(ctx, CREAM)
    rrect(ctx, x + w / 2 - 105, fy - 86, 210, 64, 14)
    ctx.set_line_width(5)
    src(ctx, cols[0] if kind not in ('plain',) else NAVY)
    ctx.stroke()
    text(ctx, sign, x + w / 2, fy - 54, 34, F_TITLE, NAVY)


def draw_street(ctx, t, cam_x, cam_z, queue=1.0, pairs_lab=0.0):
    ctx.save()
    # sky (screen space)
    g = cairo_lin(0, 0, 0, H)
    ctx.rectangle(0, 0, W, H)
    ctx.set_source(g)
    ctx.fill()
    circle(ctx, 1560 - cam_x * 0.05, 190, 70)
    fill(ctx, hexc('#FFE9A8'))
    circle(ctx, 1560 - cam_x * 0.05, 190, 100)
    fill(ctx, hexc('#FFE9A8'), 0.25)
    ctx.translate(W / 2, H * 0.55)
    ctx.scale(cam_z, cam_z)
    ctx.translate(-cam_x, -H * 0.55)
    for cx, cy, s in CLOUDS:
        x = cx + t * 12 * s - cam_x * 0.4
        for dx, dy, r in [(0, 0, 36), (34, -14, 44), (74, 0, 34), (36, 10, 34)]:
            circle(ctx, x + dx * s, cy + dy * s, r * s)
        fill(ctx, CREAM, 0.95)
    for (x, w, kind, sign, wall), hb in zip(SHOPS, HEIGHTS):
        draw_shop(ctx, x, w, kind, sign, wall, hb, t)
    # sidewalk + road
    ctx.rectangle(-800, GROUND, 6000, 70)
    fill(ctx, hexc('#E9DCC6'))
    for x in range(-800, 5200, 60):
        ctx.move_to(x, GROUND)
        ctx.line_to(x, GROUND + 70)
    ctx.set_line_width(2)
    src(ctx, hexc('#CDBB9E'))
    ctx.stroke()
    ctx.rectangle(-800, GROUND + 70, 6000, 400)
    fill(ctx, hexc('#5B6273'))
    for x in range(-800, 5200, 140):
        rrect(ctx, x, GROUND + 150, 70, 10, 5)
        fill(ctx, CREAM, 0.8)
    # queues
    if queue > 0:
        Q = [(960 - 60, -1, 7, CORAL), (960 + 60, 1, 7, MINT), (2550 - 60, -1, 5, BUTTER), (2550 + 60, 1, 5, CORAL)]
        for qx, d, n, cup in Q:
            for k in range(n):
                if k / n > queue:
                    continue
                px = qx + d * k * 46
                i = int(abs(px)) % 97
                person_side(ctx, px, GROUND + 52, 0.82, SHIRTS[i % 8], SKIN[i % 4], HAIR[(i // 3) % 4], t, px,
                            cup if k == 0 else None, face=-d)
    if pairs_lab > 0:
        for cx, lab in [(960, '奶茶店'), (2550, '快餐店'), (3470, '加油站')]:
            pill(ctx, lab, cx, 175, 40, F_TITLE, CREAM, NAVY, pairs_lab, padx=30, pady=14)
            dashed_line(ctx, cx, 205, cx, 245, NAVY, 3, (6, 6), 0, pairs_lab)
    ctx.restore()


def cairo_lin(x0, y0, x1, y1):
    import cairo
    g = cairo.LinearGradient(x0, y0, x1, y1)
    g.add_color_stop_rgba(0, *hexc('#8FD0E6'))
    g.add_color_stop_rgba(0.7, *hexc('#D8EFF0'))
    g.add_color_stop_rgba(1, *hexc('#FFF1DA'))
    return g


# ------------------------------------------------------------------ voters
VOTE_X0, VOTE_X1, VOTE_Y = 300, 1620, 800
NB = 33
COUNTS = [max(1, int(round(15 * math.exp(-((i - (NB - 1) / 2) / 7.0) ** 2)))) for i in range(NB)]


def bx(i):
    return lerp(VOTE_X0, VOTE_X1, (i + .5) / NB)


def paper(ctx):
    ctx.rectangle(0, 0, W, H)
    fill(ctx, CREAM)
    for y in range(0, H, 28):
        for x in range((y // 28 % 2) * 14, W, 28):
            circle(ctx, x, y, 1.6)
    fill(ctx, SAND_D, 0.5)


def draw_voters(ctx, t, pa, pb, reveal, alpha=1.0):
    paper(ctx)
    ctx.set_line_width(5)
    ctx.move_to(VOTE_X0 - 40, VOTE_Y + 20)
    ctx.line_to(VOTE_X1 + 40, VOTE_Y + 20)
    src(ctx, NAVY)
    ctx.stroke()
    for xx, d in [(VOTE_X0 - 40, -1), (VOTE_X1 + 40, 1)]:
        ctx.move_to(xx + d * 22, VOTE_Y + 20)
        ctx.line_to(xx, VOTE_Y + 8)
        ctx.line_to(xx, VOTE_Y + 32)
        ctx.close_path()
        fill(ctx, NAVY)
    text(ctx, '偏左', VOTE_X0 - 10, VOTE_Y + 70, 36, F_BODY, NAVY)
    text(ctx, '偏右', VOTE_X1 + 10, VOTE_Y + 70, 36, F_BODY, NAVY)
    text(ctx, '温和', (VOTE_X0 + VOTE_X1) / 2, VOTE_Y + 70, 36, F_BODY, NAVY, 0.7)
    xa, xb = lerp(VOTE_X0, VOTE_X1, pa), lerp(VOTE_X0, VOTE_X1, pb)
    bnd = (xa + xb) / 2
    tot = sum(COUNTS)
    na = 0
    for i, c in enumerate(COUNTS):
        x = bx(i)
        col = CORAL if x < bnd else MINT
        for k in range(c):
            r = clamp((reveal * (tot + 60) - (i * 3 + k * 7)) / 12)
            if r <= 0:
                continue
            y = VOTE_Y - 4 - k * 28
            pop = 1 + 0.5 * math.exp(-((x - bnd) / 18) ** 2)
            ctx.save()
            ctx.translate(x, y)
            ctx.scale(back_out(r) * pop, back_out(r) * pop)
            circle(ctx, 0, -10, 8)
            fill(ctx, col)
            rrect(ctx, -11, 0, 22, 14, 7)
            fill(ctx, col)
            ctx.restore()
        if x < bnd:
            na += c
    # candidates
    for xc, col, cold, name in [(xa, CORAL, CORAL_D, '甲'), (xb, MINT, MINT_D, '乙')]:
        dashed_line(ctx, xc, 250, xc, VOTE_Y + 10, cold, 4, (10, 8), 0, reveal)
        ctx.save()
        ctx.translate(xc, 190)
        circle(ctx, 4, 6, 56)
        fill(ctx, NAVY, 0.2 * reveal)
        circle(ctx, 0, 0, 56)
        fill(ctx, col, reveal)
        circle(ctx, 0, -12, 18)
        fill(ctx, CREAM, reveal)
        ctx.move_to(-30, 34)
        ctx.curve_to(-26, 6, 26, 6, 30, 34)
        ctx.close_path()
        fill(ctx, CREAM, reveal)
        ctx.restore()
        pill(ctx, '候选人' + name, xc + (-50 if name == '甲' else 50) * clamp((200 - abs(xa - xb)) / 100), 280, 26, F_BODY, CREAM, cold, reveal, padx=16, pady=8)
    return na / tot


# ------------------------------------------------------------------ phones
def phone(ctx, x, y, p, style, a=1.0):
    """style 0..4 old designs; p=0 old, 1 = converged modern slab."""
    olds = [  # w, h, r, keypad, screen_h_frac, color
        (150, 330, 20, 1.0, 0.35, hexc('#6FA8DC')),
        (190, 260, 60, 0.0, 0.62, hexc('#F49E4C')),
        (130, 360, 14, 1.0, 0.30, hexc('#9B8FD6')),
        (230, 300, 10, 0.0, 0.70, BUTTER),
        (160, 300, 70, 1.0, 0.40, CORAL),
    ]
    w0, h0, r0, k0, s0, c0 = olds[style]
    w, h, r, k, sf = lerp(w0, 170, p), lerp(h0, 350, p), lerp(r0, 30, p), lerp(k0, 0, p), lerp(s0, 0.92, p)
    col = lerpc(c0, hexc('#3A3F4B'), p)
    ctx.save()
    ctx.translate(x, y)
    rrect(ctx, -w / 2 + 8, -h / 2 + 10, w, h, r)
    fill(ctx, NAVY, 0.2 * a)
    rrect(ctx, -w / 2, -h / 2, w, h, r)
    fill(ctx, col, a)
    m = lerp(14, 7, p)
    sh = (h - 2 * m) * sf
    rrect(ctx, -w / 2 + m, -h / 2 + m, w - 2 * m, sh, max(4, r - m))
    g_col = lerpc(hexc('#BFE6EF'), hexc('#7FD9D2'), p)
    fill(ctx, g_col, a)
    ctx.move_to(-w / 2 + m + 10, -h / 2 + m + 10)
    ctx.line_to(-w / 2 + m + 40, -h / 2 + m + 10)
    ctx.line_to(-w / 2 + m + 10, -h / 2 + m + 60)
    ctx.close_path()
    fill(ctx, CREAM, 0.35 * a)
    if k > 0.01:
        ky = -h / 2 + m + sh + 12
        kh = h / 2 - ky - m
        for i in range(4):
            for j in range(3):
                rrect(ctx, -w / 2 + m + 4 + j * (w - 2 * m - 8) / 3, ky + i * kh / 4, (w - 2 * m - 8) / 3 - 6,
                      kh / 4 - 6, 4)
                fill(ctx, CREAM, 0.8 * k * a)
    circle(ctx, 0, -h / 2 + m + 10, 4 * p)
    fill(ctx, NAVY, a)
    ctx.restore()
