"""The beach: sea, sand, umbrellas, sunbathers, palms, measuring tape, ice-cream trucks (top-down)."""
import math
import random
import numpy as np
import cairo
from gfx import *

X0, X1 = 160, 1760          # 0 m .. 1000 m
TRACK_Y = 612
SHORE_Y = 330
BOARD_Y = 915


def m2x(m):
    return X0 + (X1 - X0) * m / 1000.0


def x2m(x):
    return (x - X0) * 1000.0 / (X1 - X0)


def shore(x, t):
    return (SHORE_Y + 9 * math.sin(x / 140 + t * 0.35) + 6 * math.sin(x / 61 - t * 0.27 + 1.3)
            + 4 * math.sin(x / 23 + 2.1))


def swash(t):
    p = (t / 6.5) % 1.0
    return 26 * (math.sin(math.pi * p) ** 2) - 6


# ------------------------------------------------------------------ static layout
rng = random.Random(7)
UMB_COLS = [(CORAL, CREAM), (MINT, CREAM), (BUTTER, CREAM), (hexc('#6FA8DC'), CREAM), (PINK, CREAM),
            (hexc('#F49E4C'), CREAM), (hexc('#9B8FD6'), CREAM)]
TOWEL_COLS = [hexc('#F7B9C4'), hexc('#9ED8E8'), hexc('#FFE08A'), hexc('#B9E3C6'), hexc('#F6C29B'), hexc('#CDBEF0')]
SKIN = [hexc('#F5CBA7'), hexc('#E0A97E'), hexc('#C68863'), hexc('#8D5B3E'), hexc('#F2D0B5')]
HAIR = [hexc('#3B2A20'), hexc('#6B4226'), hexc('#1E1B1A'), hexc('#C99A5B'), hexc('#8A3B2B')]

PEOPLE = []
N = 66
rows = [432, 478, 524, 688, 740, 792, 842]
for i in range(N):
    m = (i + 0.5) / N * 1000 + rng.uniform(-4, 4)
    y = rows[(i * 3) % len(rows)] + rng.uniform(-10, 10)
    PEOPLE.append(dict(m=m, x=m2x(m), y=y, umb=rng.random() < 0.62, uc=rng.choice(UMB_COLS), ur=rng.uniform(25, 31),
                       uang=rng.uniform(0, 6.28), tc=rng.choice(TOWEL_COLS), skin=rng.choice(SKIN),
                       hair=rng.choice(HAIR), rot=rng.uniform(-0.5, 0.5) + (math.pi / 2 if rng.random() < .5 else 0),
                       two=rng.random() < 0.3, ph=rng.uniform(0, 6.28), uoff=(rng.uniform(-14, 14), rng.uniform(-16, -6))))
PEOPLE.sort(key=lambda p: p['y'])

PALMS = [(x, BOARD_Y + 58 + rng.uniform(-8, 8), rng.uniform(55, 75), rng.uniform(0, 6.28))
         for x in [-120, 120, 420, 700, 1010, 1300, 1590, 1880, 2140]]
SHELLS = [(rng.uniform(-300, 2220), rng.uniform(370, 900), rng.uniform(2, 5), rng.random()) for _ in range(260)]
DUNES = [(rng.uniform(-300, 2220), rng.uniform(420, 880), rng.uniform(120, 300), rng.uniform(40, 90)) for _ in range(26)]
GLINTS = [(rng.uniform(-400, 2320), rng.uniform(-300, 300), rng.uniform(0.6, 2.0), rng.uniform(0, 6.28)) for _ in
          range(220)]
STEPS = []
for _ in range(9):
    x, y = rng.uniform(-200, 2100), rng.uniform(450, 880)
    a = rng.uniform(-0.6, 0.6) + (0 if rng.random() < .5 else math.pi)
    for k in range(rng.randint(8, 18)):
        a += rng.uniform(-0.15, 0.15)
        x += math.cos(a) * 15
        y += math.sin(a) * 15
        STEPS.append((x + math.cos(a + 1.57) * (4 if k % 2 else -4), y + math.sin(a + 1.57) * (4 if k % 2 else -4), a))


# ------------------------------------------------------------------ pieces
def draw_sea(ctx, t, x0=-500, x1=2420):
    sw = swash(t)
    xs = np.arange(x0, x1 + 1, 12.0)
    sh = [shore(x, t) + sw for x in xs]
    # wet sand left by the swash
    ctx.move_to(xs[0], -600)
    for x, y in zip(xs, sh):
        ctx.line_to(x, y + 34 - sw * 0.2)
    ctx.line_to(xs[-1], -600)
    ctx.close_path()
    fill(ctx, WET, 0.75)
    # water
    ctx.move_to(xs[0], -600)
    for x, y in zip(xs, sh):
        ctx.line_to(x, y)
    ctx.line_to(xs[-1], -600)
    ctx.close_path()
    g = cairo.LinearGradient(0, -200, 0, SHORE_Y + 30)
    g.add_color_stop_rgba(0, *SEA_DEEP)
    g.add_color_stop_rgba(0.62, *SEA)
    g.add_color_stop_rgba(0.9, *SEA_SH)
    g.add_color_stop_rgba(1.0, *hexc('#B9EDE4'))
    ctx.set_source(g)
    ctx.fill()
    # incoming swell lines
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    for k in range(4):
        p = ((t / 6.5) + k / 4) % 1.0
        d = 230 * (1 - p) + 10
        a = math.sin(math.pi * p) ** 1.5 * 0.55
        ctx.set_line_width(2.5 + 3 * p)
        for seg in range(0, len(xs) - 1, 14):
            ctx.move_to(xs[seg], sh[seg] - d + 6 * math.sin(xs[seg] / 40 + k))
            for j in range(seg, min(seg + 11, len(xs))):
                ctx.line_to(xs[j], sh[j] - d * (1 + 0.04 * math.sin(xs[j] / 90 + k * 2)) + 5 * math.sin(xs[j] / 40 + k))
        src(ctx, FOAM, a)
        ctx.stroke()
    # glints
    for gx, gy, s, ph in GLINTS:
        a = max(0.0, math.sin(t * 2.2 * s + ph)) ** 10
        if a < 0.05:
            continue
        ctx.move_to(gx - 5 * s, gy)
        ctx.line_to(gx + 5 * s, gy)
        ctx.move_to(gx, gy - 2.5 * s)
        ctx.line_to(gx, gy + 2.5 * s)
        ctx.set_line_width(1.6)
        src(ctx, FOAM, a * 0.9)
        ctx.stroke()
    # foam lace at waterline
    for wdt, off, a in [(16, 2, 0.35), (7, 0, 0.95), (3, 9, 0.6)]:
        ctx.move_to(xs[0], sh[0] + off)
        for i, (x, y) in enumerate(zip(xs, sh)):
            ctx.line_to(x, y + off + 2.5 * math.sin(x / 9 + t * 1.3 + off))
        ctx.set_line_width(wdt)
        src(ctx, FOAM, a)
        ctx.stroke()


def draw_sand(ctx, t, sun):
    ctx.rectangle(-600, SHORE_Y - 40, 3100, 1400)
    fill(ctx, SAND)
    for x, y, rx, ry in DUNES:
        ellipse(ctx, x, y, rx, ry)
        fill(ctx, SAND_D, 0.22)
    for x, y, a in STEPS:
        ellipse(ctx, x, y, 4.2, 2.4, a)
        fill(ctx, SAND_D, 0.8)
    for x, y, r, k in SHELLS:
        if k < 0.7:
            circle(ctx, x, y, r * 0.5)
            fill(ctx, SAND_D, 0.9)
        else:
            ellipse(ctx, x, y, r, r * 0.7, k * 9)
            fill(ctx, CREAM if k < 0.85 else PINK, 0.95)


def draw_board(ctx, t, sun):
    y = BOARD_Y
    ctx.rectangle(-600, y, 3100, 600)
    fill(ctx, hexc('#D7A06F'))
    ctx.set_line_width(2)
    for x in range(-600, 2500, 22):
        ctx.move_to(x, y)
        ctx.line_to(x, y + 600)
    src(ctx, hexc('#B97F50'), 0.6)
    ctx.stroke()
    ctx.rectangle(-600, y - 6, 3100, 12)
    fill(ctx, hexc('#B97F50'))
    ctx.rectangle(-600, y + 2, 3100, 4)
    fill(ctx, hexc('#E9BB8C'))


def draw_palm(ctx, x, y, r, a0, t, sun):
    sx, sy = sun['sx'], sun['sy']
    for shadow in (1, 0):
        ctx.save()
        if shadow:
            ctx.translate(x + sx * 46, y + sy * 46)
        else:
            ctx.translate(x, y)
        ctx.rotate(a0 + 0.03 * math.sin(t * 0.9 + a0))
        for i in range(9):
            a = i * 2 * math.pi / 9 + 0.15 * math.sin(i * 7.1)
            rr = r * (0.85 + 0.2 * math.sin(i * 3.3))
            ctx.save()
            ctx.rotate(a)
            ctx.move_to(0, 0)
            ctx.curve_to(rr * 0.3, -rr * 0.28, rr * 0.75, -rr * 0.22, rr, 0.08 * rr)
            ctx.curve_to(rr * 0.7, rr * 0.12, rr * 0.3, rr * 0.16, 0, 0)
            if shadow:
                fill(ctx, NAVY, 0.16 * sun['sh'])
            else:
                fill(ctx, hexc('#3E9E6E') if i % 2 else hexc('#5DBB7C'))
                ctx.move_to(4, 0)
                ctx.curve_to(rr * 0.3, -rr * 0.12, rr * 0.7, -rr * 0.08, rr * 0.95, 0.06 * rr)
                ctx.set_line_width(1.5)
                src(ctx, hexc('#2C7A54'), 0.7)
                ctx.stroke()
            ctx.restore()
        if not shadow:
            circle(ctx, 0, 0, 7)
            fill(ctx, hexc('#8A5A3B'))
        ctx.restore()


def draw_umbrella(ctx, x, y, r, cols, ang, sun, a=1.0):
    sx, sy = sun['sx'], sun['sy']
    circle(ctx, x + sx * 20, y + sy * 20, r)
    fill(ctx, NAVY, 0.18 * sun['sh'] * a)
    n = 8
    for i in range(n):
        ctx.move_to(x, y)
        ctx.arc(x, y, r, ang + i * 2 * math.pi / n, ang + (i + 1) * 2 * math.pi / n)
        ctx.close_path()
        fill(ctx, cols[i % 2], a)
    # scalloped rim shading
    circle(ctx, x, y, r)
    ctx.set_line_width(2)
    src(ctx, NAVY, 0.15 * a)
    ctx.stroke()
    circle(ctx, x, y, 3.5)
    fill(ctx, CREAM, a)


def draw_person_lying(ctx, x, y, rot, skin, hair, tc, sun):
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(rot)
    sx, sy = sun['sx'], sun['sy']
    rrect(ctx, -13 + sx * 3, -25 + sy * 3, 26, 50, 4)
    fill(ctx, NAVY, 0.12 * sun['sh'])
    rrect(ctx, -13, -25, 26, 50, 4)
    fill(ctx, tc)
    for k in range(3):
        ctx.rectangle(-13, -18 + k * 16, 26, 4)
        fill(ctx, CREAM, 0.7)
    # body
    ellipse(ctx, 0, 2, 6.5, 12)
    fill(ctx, skin)
    ctx.set_line_width(3.4)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    src(ctx, skin)
    for s in (-1, 1):
        ctx.move_to(s * 5, -6)
        ctx.line_to(s * 10, 6)
        ctx.move_to(s * 3, 12)
        ctx.line_to(s * 4, 22)
    ctx.stroke()
    rrect(ctx, -6, 6, 12, 7, 2)
    fill(ctx, tc if tc != CORAL else MINT)
    circle(ctx, 0, -14, 5.5)
    fill(ctx, skin)
    ctx.arc(0, -14, 5.7, math.pi * 0.9, math.pi * 2.1)
    fill(ctx, hair)
    ctx.restore()


def cone_badge(ctx, x, y, col, s=1.0, a=1.0):
    if a <= 0.01 or s <= 0.01:
        return
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(s, s)
    circle(ctx, 1.5, 2.5, 12)
    fill(ctx, NAVY, 0.25 * a)
    circle(ctx, 0, 0, 12)
    fill(ctx, col, a)
    circle(ctx, 0, 0, 12)
    ctx.set_line_width(2.2)
    src(ctx, CREAM, a)
    ctx.stroke()
    ctx.move_to(-4.6, -1)
    ctx.line_to(4.6, -1)
    ctx.line_to(0, 8.5)
    ctx.close_path()
    fill(ctx, hexc('#F3C27A'), a)
    circle(ctx, 0, -3.5, 4.8)
    fill(ctx, CREAM, a)
    ctx.restore()


def draw_people(ctx, t, S, sun):
    hl = S.get('hl_idx')
    for i, p in enumerate(PEOPLE):
        jig = 0
        draw_person_lying(ctx, p['x'], p['y'], p['rot'], p['skin'], p['hair'], p['tc'], sun)
        if p['two']:
            draw_person_lying(ctx, p['x'] + 26, p['y'] + 4, p['rot'] + 0.2, SKIN[(i + 2) % 5], HAIR[(i + 1) % 5],
                              TOWEL_COLS[(i + 3) % 6], sun)
    for p in PEOPLE:
        if p['umb']:
            draw_umbrella(ctx, p['x'] + p['uoff'][0], p['y'] + p['uoff'][1], p['ur'], p['uc'],
                          p['uang'] + 0.05 * math.sin(t * 0.6 + p['ph']), sun)


def choice(m, A, B):
    if A is None and B is None:
        return None
    if A is None:
        return 'B'
    if B is None:
        return 'A'
    return 'A' if abs(m - A) < abs(m - B) or (abs(m - A) == abs(m - B) and m < 500) else 'B'


def draw_badges(ctx, t, S):
    vis = S.get('icons', 0)
    if vis <= 0:
        return
    A, B = S.get('A'), S.get('B')
    reveal = S.get('icon_reveal', 1e9)    # meters from the reveal origin
    origin = S.get('icon_origin', 500)
    bnd = (A + B) / 2 if (A is not None and B is not None) else None
    for i, p in enumerate(PEOPLE):
        d = abs(p['m'] - origin)
        r = clamp((reveal - d) / 60)
        if r <= 0:
            continue
        c = choice(p['m'], A, B)
        col = CORAL if c == 'A' else MINT
        pop = 0
        if bnd is not None:
            pop = math.exp(-((p['m'] - bnd) / 14) ** 2) * 0.55
        s = back_out(r) * (1 + pop) * S.get('icon_scale', 1.0)
        bob = 2.5 * math.sin(t * 2.4 + p['ph'])
        cone_badge(ctx, p['x'], p['y'] - 34 + bob, col, s, vis)


def draw_truck(ctx, x, y, col, cold, scoop, dirn, t, sun, moving=False, label=None, la=1.0, sc=1.0, kind='A', lx=0):
    ctx.save()
    ctx.translate(x, y)
    bounce = 1.2 * math.sin(t * 40) if moving else 0
    ctx.scale(sc * dirn, sc)
    L, Wd = 100, 50
    sx, sy = sun['sx'], sun['sy']
    for k, a in [(16, 0.07), (11, 0.09), (7, 0.12)]:
        rrect(ctx, -L / 2 + sx * k * dirn, -Wd / 2 + sy * k, L, Wd, 12)
        fill(ctx, NAVY, a * sun['sh'] * 1.4)
    # wheels
    for wx in (-30, 28):
        for s in (-1, 1):
            rrect(ctx, wx - 9, s * Wd / 2 - 5, 18, 10, 4)
            fill(ctx, hexc('#2A2A33'))
    ctx.translate(0, bounce * 0.3)
    rrect(ctx, -L / 2, -Wd / 2, L, Wd, 12)
    fill(ctx, col)
    # cab + windshield (front = +x)
    rrect(ctx, L / 2 - 30, -Wd / 2 + 5, 22, Wd - 10, 6)
    fill(ctx, hexc('#2F4F6F'))
    rrect(ctx, L / 2 - 28, -Wd / 2 + 8, 6, Wd - 16, 3)
    fill(ctx, hexc('#9FD3E6'), 0.8)
    # roof with striped awning
    rrect(ctx, -L / 2 + 6, -Wd / 2 + 4, L - 40, Wd - 8, 8)
    fill(ctx, CREAM)
    ctx.save()
    rrect(ctx, -L / 2 + 6, -Wd / 2 + 4, L - 40, Wd - 8, 8)
    ctx.clip()
    for k in range(7):
        ctx.rectangle(-L / 2 + 6 + k * 18, -Wd, 9, Wd * 2)
        fill(ctx, col, 0.85)
    ctx.restore()
    # headlights
    for s in (-1, 1):
        circle(ctx, L / 2 - 3, s * 15, 3.5)
        fill(ctx, BUTTER)
    # giant scoop on the roof
    cx = -L / 2 + 6 + (L - 40) / 2
    circle(ctx, cx + 3, 3, 21)
    fill(ctx, NAVY, 0.2)
    for k in range(8):
        a = k * math.pi / 4 + 0.3
        circle(ctx, cx + 19 * math.cos(a), 19 * math.sin(a), 6)
        fill(ctx, scoop)
    circle(ctx, cx, 0, 19)
    fill(ctx, scoop)
    circle(ctx, cx - 6, -6, 6)
    fill(ctx, CREAM, 0.55)
    if kind == 'A':
        circle(ctx, cx + 3, 1, 5.5)
        fill(ctx, RED)
        circle(ctx, cx + 1.5, -0.5, 1.8)
        fill(ctx, CREAM, 0.8)
    else:
        for s in (-1, 1):
            ellipse(ctx, cx + 3 + s * 4, 1, 6, 3, s * 0.6)
            fill(ctx, hexc('#2E9A5C'))
    ctx.restore()
    if label and la > 0.01:
        pill(ctx, label, x + lx, y + 58 * sc, 26, F_BODY, CREAM, cold, la, padx=18, pady=8)


def draw_tape(ctx, t, p, hl=()):
    """Measuring tape along the sand; p = unroll progress."""
    if p <= 0:
        return
    y = 878
    xe = lerp(X0, X1, p)
    rrect(ctx, X0 - 6 + 3, y - 13 + 4, xe - X0 + 12, 26, 5)
    fill(ctx, NAVY, 0.18)
    rrect(ctx, X0 - 6, y - 13, xe - X0 + 12, 26, 5)
    fill(ctx, BUTTER)
    ctx.set_line_width(2)
    src(ctx, NAVY, 0.85)
    for m in range(0, 1001, 25):
        x = m2x(m)
        if x > xe:
            break
        ln = 12 if m % 250 == 0 else 7 if m % 50 == 0 else 4
        ctx.move_to(x, y - 13)
        ctx.line_to(x, y - 13 + ln)
    ctx.stroke()
    for m in range(0, 1001, 250):
        x = m2x(m)
        if x > xe:
            break
        hi = m in hl
        text(ctx, f'{m}m' if m in (0, 1000) else str(m), x, y + 5, 15 if not hi else 17, F_NUM,
             RED if hi else NAVY, 1.0)
    # case at the end
    circle(ctx, xe + 40, y, 20)
    fill(ctx, CORAL_D)
    circle(ctx, xe + 40, y, 9)
    fill(ctx, CREAM)


def draw_world(ctx, t, S):
    sun = S['sun']
    draw_sand(ctx, t, sun)
    draw_sea(ctx, t)
    # territory tint
    A, B = S.get('A'), S.get('B')
    ta = S.get('tint', 0)
    if ta > 0 and A is not None and B is not None:
        bx = m2x((A + B) / 2)
        ctx.save()
        ctx.set_operator(cairo.OPERATOR_HSL_COLOR)
        ctx.rectangle(X0, SHORE_Y + 40, bx - X0, BOARD_Y - SHORE_Y - 40)
        fill(ctx, CORAL, 0.55 * ta)
        ctx.rectangle(bx, SHORE_Y + 40, X1 - bx, BOARD_Y - SHORE_Y - 40)
        fill(ctx, hexc('#3CC8B4'), 0.6 * ta)
        ctx.restore()
        for xx in (X0, X1):
            dashed_line(ctx, xx, SHORE_Y + 40, xx, BOARD_Y - 10, NAVY, 2, (4, 8), 0, 0.35 * ta)
    # truck track
    ctx.save()
    ctx.set_line_width(2)
    for dy in (-15, 15):
        ctx.move_to(-600, TRACK_Y + dy)
        for x in range(-600, 2600, 40):
            ctx.line_to(x, TRACK_Y + dy + 1.5 * math.sin(x * 0.05))
    ctx.set_dash((6, 7))
    src(ctx, SAND_D, 0.9)
    ctx.stroke()
    ctx.restore()
    draw_board(ctx, t, sun)
    for x, y, r, a in PALMS:
        pass
    draw_people(ctx, t, S, sun)
    if ta > 0 and A is not None and B is not None and S.get('bline', 0) > 0:
        bx = m2x((A + B) / 2)
        ba = S['bline']
        dashed_line(ctx, bx, SHORE_Y + 50, bx, BOARD_Y - 20, NAVY, 4, (14, 10), -t * 30, 0.85 * ba)
        ctx.move_to(bx, SHORE_Y + 50)
        ctx.line_to(bx + 34, SHORE_Y + 62)
        ctx.line_to(bx, SHORE_Y + 74)
        ctx.close_path()
        fill(ctx, BUTTER, ba)
        ctx.move_to(bx, SHORE_Y + 50)
        ctx.line_to(bx, SHORE_Y + 80)
        ctx.set_line_width(3)
        src(ctx, NAVY, ba)
        ctx.stroke()
    draw_tape(ctx, t, S.get('tape', 0), S.get('tape_hl', ()))
    for x, y, r, a in PALMS:
        draw_palm(ctx, x, y, r, a, t, sun)
