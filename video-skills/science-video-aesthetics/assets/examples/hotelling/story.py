"""Timeline: what is on screen at global time t, plus sound cues."""
import math
import numpy as np
import cairo
from gfx import *
import world as Wd
from world import m2x, TRACK_Y, PEOPLE
import street as St

DUR = 160.0

# ------------------------------------------------------------------ truck tracks (meters)
A = Track(475, [
    (6.25, 6.95, -170, 'in'),
    (12.0, 15.0, 120, 'out'),
    (31.0, 34.0, 250, 'io'),
    (52.0, 54.0, 350, 'io'),
    (62.5, 63.7, 430, 'io'),
    (66.5, 67.3, 475, 'io'),
    (84.5, 86.0, 370, 'io'),
    (88.0, 89.0, 475, 'io'),
])
B = Track(525, [
    (6.25, 6.95, 1170, 'in'),
    (12.4, 15.4, 880, 'out'),
    (31.2, 34.2, 750, 'io'),
    (59.5, 61.0, 650, 'io'),
    (64.7, 65.7, 570, 'io'),
    (68.0, 68.7, 525, 'in'),
    (89.8, 91.3, 630, 'io'),
    (92.8, 93.8, 525, 'io'),
])
MOVES = [(m[0], m[1], 'A') for m in A.moves] + [(m[0], m[1], 'B') for m in B.moves]

CAM_X = Track(960, [(3.3, 5.6, 960, 'out'), (18.0, 19.5, 820, 'io'), (23.0, 25.0, 960, 'io'),
                    (47.6, 49.5, m2x(250), 'io'), (51.8, 54.5, 960, 'io'), (58.8, 60.0, 1040, 'io'),
                    (61.0, 62.3, 960, 'io'), (73.5, 75.5, 960, 'io'), (94.0, 95.0, 960, 'io')])
CAM_Y = Track(600, [(3.3, 5.6, 560, 'out'), (18.0, 19.5, 600, 'io'), (23.0, 25.0, 560, 'io'),
                    (47.6, 49.5, 600, 'io'), (51.8, 54.5, 580, 'io'), (61.0, 62.3, 600, 'io'),
                    (73.5, 75.5, 560, 'io'), (94.0, 95.0, 600, 'io'), (99.5, 101, 560, 'io')])
CAM_Z = Track(1.9, [(3.3, 5.6, 1.0, 'out'), (7.0, 12.0, 1.04, 'io'), (18.0, 19.5, 1.45, 'io'), (23.0, 25.0, 1.0, 'io'),
                    (47.6, 49.5, 1.7, 'io'), (51.8, 54.5, 1.15, 'io'), (58.8, 60.0, 1.25, 'io'),
                    (61.0, 62.3, 1.2, 'io'), (62.5, 68.6, 1.75, 'in'), (73.5, 75.5, 1.0, 'io'),
                    (94.0, 95.0, 1.55, 'out'), (99.5, 101, 1.0, 'io')])
CAM_END = Track(1.9, [(148.0, 156.0, 1.0, 'io')])
DAY = Track(0.5, [(6.9, 7.0, 0.12, 'lin'), (7.0, 106.0, 0.62, 'lin'), (147.0, 147.1, 0.97, 'lin')])

WIPES = [3.25, 118.0, 127.3, 138.3, 148.0]

CAPS = [
    (3.6, 6.1, '答案，藏在一片沙滩上'),
    (7.3, 11.8, '一片 1000 米长的沙滩\n游客均匀地躺满了整条海岸线'),
    (12.3, 17.8, '来了两辆冰淇淋车\n口味一样，价格也一样'),
    (18.3, 23.6, '游客都很懒：\n谁离得近，就去谁那儿买'),
    (24.0, 30.4, '问题来了：\n两辆车停在哪里最好？'),
    (31.0, 36.8, '对游客来说，最好的停法是——\n一辆在 1/4 处，一辆在 3/4 处'),
    (37.1, 42.4, '每个人最多走 250 米\n平均只要走 125 米'),
    (42.7, 47.4, '两家平分沙滩，各占一半\n看起来，皆大欢喜？'),
    (47.8, 51.8, '可是草莓车的老板\n动了一个小心思……'),
    (54.3, 59.2, '左边的客人跑不掉，离他还是最近\n分界线却右移了——白捡一块地盘！'),
    (59.4, 62.4, '薄荷车当然不干'),
    (62.7, 68.4, '你挪一步，我挪一步……'),
    (68.8, 73.4, '直到——两辆车贴在了一起'),
    (73.7, 79.6, '折腾了一大圈\n结果还是五五开'),
    (80.0, 84.1, '那么现在，谁想离开中间？'),
    (84.3, 89.3, '草莓车往左一退\n地盘立刻被对手吃掉'),
    (89.6, 94.0, '薄荷车往右一退，也一样'),
    (94.3, 99.8, '谁先离开谁吃亏，于是谁都不动\n这就是「纳什均衡」'),
    (100.1, 105.8, '可游客遭了殃：最远的人要走 500 米\n平均路程翻了一倍'),
    (111.3, 117.6, '只要竞争者拼的是「位置」\n就会一步步挤向中间，最后几乎一模一样'),
    (118.4, 122.9, '所以奶茶店、快餐店、加油站……\n总爱紧挨着开'),
    (123.2, 127.0, '（扎堆还能共享客流：\n逛街的人更爱去店多的地方）'),
    (127.8, 132.6, '选举也一样：两位候选人\n都在争抢「中间选民」'),
    (132.9, 137.9, '于是政见越来越温和\n也越来越像'),
    (138.6, 143.4, '手机越长越像，爆款越来越同质\n——都在往「中间」挤'),
    (143.7, 147.7, '因为中间\n离最多的人最近'),
    (148.6, 152.4, '下次看到两家店紧挨着开\n别以为是巧合'),
    (152.7, 155.6, '那是一场博弈的终点'),
]

# floating deltas: (t, text, colour, meter)
DELTAS = [(54.0, '+5%', CORAL, 520), (61.0, '+5%', MINT_D, 520), (63.7, '+4%', CORAL, 520), (65.7, '+4%', MINT_D, 520),
          (67.3, '+2%', CORAL, 520), (68.7, '+2%', MINT_D, 520),
          (86.0, '−5%', RED, 450), (91.3, '−5%', RED, 560)]

BUBBLES = [(48.6, 52.2, 'A', '要是我往中间挪一点……？'), (59.6, 62.4, 'B', '那我也挪！'),
           (86.2, 88.0, 'A', '亏了亏了！'), (91.4, 92.8, 'B', '快回去！')]

HL = min(range(len(PEOPLE)), key=lambda i: abs(PEOPLE[i]['m'] - 375) + abs(PEOPLE[i]['y'] - 500) * 0.3)


def beach_state(t):
    S = dict(sun=sun(t), A=A(t), B=B(t))
    if t < 7:     # hook end-state
        S.update(tint=1 - smooth((t - 6.2) / 0.5), bline=1 - smooth((t - 6.2) / 0.5), icons=1 - smooth((t - 6.2) / 0.4),
                 tape=1 - smooth((t - 6.2) / 0.5))
        return S
    S['tape'] = ease_io((t - 8.0) / 2.6)
    S['icons'] = 1.0 if t >= 20.5 else 0.0
    S['icon_origin'] = PEOPLE[HL]['m']
    S['icon_reveal'] = (t - 22.6) * 600 if t < 25 else 1e9
    S['tint'] = smooth((t - 24.2) / 1.0)
    S['bline'] = smooth((t - 24.8) / 0.8)
    if 31 < t < 48:
        S['tape_hl'] = (250, 750)
    if t > 120:
        S.update(tint=1, bline=0.0, icons=1, tape=1, icon_reveal=1e9)
    return S


def sun(t):
    d = DAY(t)
    return dict(sx=lerp(-0.9, 0.95, d), sy=0.45 + 0.25 * abs(d - 0.5), sh=1.0, day=d)


# ------------------------------------------------------------------ overlays (screen space)
def caption(ctx, t):
    for a, b, s in CAPS:
        if a <= t <= b:
            al = win(t, a, b, 0.25, 0.3)
            k = ease_out((t - a) / 0.35)
            y = 1000 - (s.count('\n')) * 26 + (1 - k) * 18
            w, h = text_size(s, 44, F_BODY)
            ctx.save()
            rrect(ctx, W / 2 - w / 2 - 26, y - h / 2 - 12 + 6, w + 52, h + 24, 26)
            fill(ctx, NAVY, 0.25 * al)
            rrect(ctx, W / 2 - w / 2 - 26, y - h / 2 - 12, w + 52, h + 24, 26)
            fill(ctx, CREAM, 0.94 * al)
            ctx.restore()
            text(ctx, s, W / 2, y, 44, F_BODY, NAVY, al)


def scoreboard(ctx, t, share, a, la='草莓车', lb='薄荷车'):
    if a <= 0.01:
        return
    y = 66
    bw, bh = 760, 44
    x0 = W / 2 - bw / 2
    ctx.save()
    ctx.translate(0, -(1 - ease_out(a)) * 40)
    rrect(ctx, x0 - 8 + 4, y - bh / 2 - 8 + 6, bw + 16, bh + 16, (bh + 16) / 2)
    fill(ctx, NAVY, 0.25 * a)
    rrect(ctx, x0 - 8, y - bh / 2 - 8, bw + 16, bh + 16, (bh + 16) / 2)
    fill(ctx, CREAM, a)
    ctx.save()
    rrect(ctx, x0, y - bh / 2, bw, bh, bh / 2)
    ctx.clip()
    ctx.rectangle(x0, y - bh / 2, bw * share, bh)
    fill(ctx, CORAL, a)
    ctx.rectangle(x0 + bw * share, y - bh / 2, bw * (1 - share), bh)
    fill(ctx, MINT, a)
    ctx.restore()
    ctx.move_to(W / 2, y - bh / 2 - 6)
    ctx.line_to(W / 2, y + bh / 2 + 6)
    ctx.set_line_width(2)
    src(ctx, NAVY, 0.5 * a)
    ctx.stroke()
    pa = int(round(share * 100))
    text(ctx, f'{pa}%', x0 + 50, y + 1, 30, F_NUM, CREAM, a)
    text(ctx, f'{100 - pa}%', x0 + bw - 50, y + 1, 30, F_NUM, CREAM, a)
    pill(ctx, la, x0 - 90, y, 28, F_BODY, CREAM, CORAL_D, a, padx=18, pady=10, shadow=False)
    pill(ctx, lb, x0 + bw + 90, y, 28, F_BODY, CREAM, MINT_D, a, padx=18, pady=10, shadow=False)
    ctx.restore()


def bubble(ctx, x, y, s, a, k):
    if a <= 0.01:
        return
    w, h = text_size(s, 36, F_BODY)
    sc = back_out(k)
    if sc < 1e-3:
        return
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(sc, sc)
    bw, bh = w + 40, h + 26
    for off, c, al in [((5, 7), NAVY, 0.25), ((0, 0), CREAM, 1)]:
        ctx.save()
        ctx.translate(*off)
        rrect(ctx, -bw / 2, -bh - 26, bw, bh, 22)
        ctx.move_to(-14, -30)
        ctx.line_to(0, 0)
        ctx.line_to(16, -30)
        fill(ctx, c, al * a)
        ctx.restore()
    text(ctx, s, 0, -bh / 2 - 26, 36, F_BODY, NAVY, a)
    ctx.restore()


def world_to_screen(x, y, cam):
    cx, cy, z = cam
    return (x - cx) * z + W / 2, (y - cy) * z + H / 2


def stamp(ctx, t, t0, s1, s2):
    k = (t - t0)
    if k < 0:
        return
    a = min(1, k / 0.12) * (1 - smooth((t - 99.6) / 0.5))
    sc = lerp(2.2, 1.0, ease_out(k / 0.25)) + 0.04 * math.sin(k * 30) * math.exp(-k * 6)
    ctx.save()
    ctx.translate(W / 2, 330)
    ctx.rotate(-0.08)
    ctx.scale(sc, sc)
    w, h = text_size(s1, 92, F_TITLE)
    rrect(ctx, -w / 2 - 40, -h / 2 - 30, w + 80, h + 80, 26)
    fill(ctx, CREAM, 0.92 * a)
    rrect(ctx, -w / 2 - 40, -h / 2 - 30, w + 80, h + 80, 26)
    ctx.set_line_width(9)
    src(ctx, RED, a)
    ctx.stroke()
    text(ctx, s1, 0, -8, 92, F_TITLE, RED, a)
    text(ctx, s2, 0, h / 2 + 22, 26, F_NUM, RED, a)
    ctx.restore()


def draw_beach(ctx, t, cam, extra=True):
    S = beach_state(t)
    cx, cy, z = cam
    shake = 0
    if 68.7 <= t < 69.3:
        k = (t - 68.7)
        shake = 10 * math.exp(-k * 9) * math.sin(k * 70)
    ctx.save()
    ctx.translate(W / 2 + shake, H / 2 + shake * 0.6)
    ctx.scale(z, z)
    ctx.translate(-cx, -cy)
    Wd.draw_world(ctx, t, S)
    sn = S['sun']
    a, b = S['A'], S['B']
    # demo: distances from one sunbather
    if 18.6 < t < 24.5:
        p = PEOPLE[HL]
        al = win(t, 18.6, 24.5, 0.4, 0.5)
        for m, col, k0 in [(a, CORAL, 19.2), (b, MINT, 20.0)]:
            k = ease_io((t - k0) / 0.8)
            if k <= 0:
                continue
            tx = m2x(m)
            ex, ey = lerp(p['x'], tx, k), lerp(p['y'], TRACK_Y, k)
            dashed_line(ctx, p['x'], p['y'], ex, ey, col, 5, (12, 9), -t * 40, al)
            if k > 0.95:
                d = abs(p['m'] - m)
                pill(ctx, f'{int(round(d / 10) * 10)} 米', (p['x'] + tx) / 2, (p['y'] + TRACK_Y) / 2 - 20, 30, F_BODY,
                     CREAM, col, al * smooth((k - 0.95) * 20), padx=18, pady=8)
        circle(ctx, p['x'], p['y'], 46 + 4 * math.sin(t * 5))
        ctx.set_line_width(4)
        src(ctx, NAVY, 0.8 * al)
        ctx.stroke()
        if t > 20.5:
            Wd.cone_badge(ctx, p['x'], p['y'] - 36, CORAL, back_out((t - 20.5) / 0.4) * 1.6, al)
    if S.get('icons', 0) > 0 and not (18.6 < t < 22.6):
        Wd.draw_badges(ctx, t, S)
    # optimum distance brackets
    if 37.0 < t < 47.5:
        al = win(t, 37.0, 47.5, 0.4, 0.5)
        y = 838
        for m0, m1, col, k0 in [(0, 250, CORAL, 37.3), (250, 500, CORAL, 37.7), (500, 750, MINT, 38.1),
                                (750, 1000, MINT, 38.5)]:
            k = ease_out((t - k0) / 0.5)
            x0, x1 = m2x(m0) + 6, m2x(m0 + (m1 - m0) * k) - 6
            if k <= 0:
                continue
            rrect(ctx, x0, y - 5, x1 - x0, 10, 5)
            fill(ctx, col, al)
            for xx in (x0, x1):
                rrect(ctx, xx - 3, y - 16, 6, 32, 3)
                fill(ctx, col, al)
            if k > 0.9:
                pill(ctx, '≤250m', (x0 + x1) / 2, y - 34, 24, F_NUM, CREAM, col, al, padx=14, pady=6)
    # equilibrium walk lengths
    if 100.0 < t < 106.5:
        al = win(t, 100.0, 106.5, 0.4, 0.4)
        y = 838
        for m0, m1, col, k0 in [(0, 475, CORAL, 100.3), (1000, 525, MINT, 100.6)]:
            k = ease_out((t - k0) / 0.9)
            x0, x1 = m2x(m0), m2x(lerp(m0, m1, k))
            rrect(ctx, min(x0, x1), y - 6, abs(x1 - x0), 12, 6)
            fill(ctx, col, al)
            for xx in (x0, x1):
                rrect(ctx, xx - 3, y - 18, 6, 36, 3)
                fill(ctx, col, al)
            if k > 0.9:
                pill(ctx, '最远 500 米', (x0 + x1) / 2, y - 40, 30, F_BODY, CREAM, col, al, padx=18, pady=8)
    # trucks
    for name, m, col, cold, scoop, lab, kind in [('A', a, CORAL, CORAL_D, PINK, '草莓车', 'A'),
                                                ('B', b, MINT, MINT_D, hexc('#BFF0DA'), '薄荷车', 'B')]:
        tr = A if name == 'A' else B
        mv = tr.moving(t)
        v = tr(t + 0.05) - tr(t - 0.05)
        dirn = 1 if name == 'A' else -1
        if abs(v) > 0.2:
            dirn = 1 if v > 0 else -1
        x = m2x(m)
        if mv:   # dust puffs behind
            for k in range(5):
                ph = (t * 3 + k / 5) % 1
                circle(ctx, x - dirn * (60 + ph * 50), TRACK_Y + 18 * math.sin(k * 2.1) * 0.6 + 6,
                       6 + ph * 12)
                fill(ctx, SAND_D, (1 - ph) * 0.6)
        la = smooth((t - 14.3) / 0.6) if t > 7 else 1.0
        if t > 6.2 and t < 7.0:
            la = 1 - smooth((t - 6.2) / 0.3)
        lx = (-1 if name == 'A' else 1) * 42 * clamp((140 - abs(a - b)) / 60)
        Wd.draw_truck(ctx, x, TRACK_Y, col, cold, scoop, dirn, t, sn, mv, lab, la, 1.25, kind, lx)
    # bubbles
    for t0, t1, who, s in BUBBLES:
        if t0 <= t <= t1:
            m = a if who == 'A' else b
            bubble(ctx, m2x(m), TRACK_Y - 46, s, win(t, t0, t1, 0.15, 0.25), (t - t0) / 0.35)
    # deltas
    for t0, s, col, m in DELTAS:
        k = (t - t0) / 1.5
        if 0 <= k <= 1:
            text(ctx, s, m2x((a + b) / 2), SHORE_Y_D - 10 - 60 * ease_out(k), 54, F_NUM, CREAM, 1 - smooth((k - .6) / .4),
                 stroke=6, stroke_color=tuple(col), scale=back_out(min(1, k * 4)))
    ctx.restore()
    return S


SHORE_Y_D = Wd.SHORE_Y + 110


def wipe(ctx, t):
    for t0 in WIPES:
        k = (t - t0 + 0.4) / 0.8
        if 0 < k < 1:
            ctx.save()
            off = lerp(-2600, 2600, ease_io(k))
            ctx.translate(W / 2 + off, H / 2)
            ctx.rotate(0.35)
            cols = [CORAL, CREAM, MINT, CREAM, BUTTER, CREAM, CORAL]
            bw = 2300 / len(cols)
            for i, c in enumerate(cols):
                ctx.rectangle(-1150 + i * bw, -1600, bw + 1, 3200)
                fill(ctx, c)
            ctx.restore()


def hook_title(ctx, t):
    if t > 3.4:
        return
    a = 1 - smooth((t - 3.0) / 0.3)
    sc = lerp(1.18, 1.0, ease_out(t / 0.35)) + 0.02 * math.sin(t * 2)
    ctx.save()
    ctx.translate(W / 2, 330)
    ctx.scale(sc, sc)
    ctx.rotate(-0.03)
    text(ctx, '为什么两家奶茶店\n总开在隔壁？', 0, 0, 116, F_TITLE, CREAM, a, stroke=10, stroke_color=tuple(NAVY),
         shadow=8, spacing=0.12)
    ctx.restore()
    if t > 1.2:
        k = (t - 1.2) / 0.35
        pill(ctx, '不是巧合，是一场博弈', W / 2, 475, 44, F_BODY, CREAM, CORAL_D, a, scale=back_out(k), padx=34, pady=16)


def law_card(ctx, t):
    a = win(t, 106.0, 118.2, 0.6, 0.3)
    if a <= 0:
        return
    ctx.rectangle(0, 0, W, H)
    fill(ctx, NAVY, 0.55 * a)
    k = ease_out((t - 106.0) / 0.7)
    ctx.save()
    ctx.translate(W / 2, 470 + (1 - k) * 80)
    ctx.rotate(-0.015)
    cw, ch = 1180, 640
    rrect(ctx, -cw / 2 + 10, -ch / 2 + 14, cw, ch, 30)
    fill(ctx, NAVY, 0.4 * a)
    rrect(ctx, -cw / 2, -ch / 2, cw, ch, 30)
    fill(ctx, CREAM, a)
    ctx.save()
    rrect(ctx, -cw / 2, -ch / 2, cw, ch, 30)
    ctx.clip()
    for i in range(24):
        ctx.rectangle(-cw / 2 + i * cw / 24, -ch / 2, cw / 48, 26)
        fill(ctx, CORAL if i % 2 else MINT, a)
    ctx.restore()
    text(ctx, '霍特林定律', 0, -160, 128, F_TITLE, NAVY, a)
    text(ctx, "HOTELLING'S LAW  ·  1929", 0, -52, 34, F_NUM, CORAL_D, a)
    a2 = a * smooth((t - 107.6) / 0.5)
    text(ctx, '经济学家哈罗德·霍特林在论文《竞争中的稳定性》中提出', 0, 30, 34, F_LIGHT, NAVY, a2)
    a3 = a * smooth((t - 108.8) / 0.5)
    text(ctx, '两个竞争者会不断向中间靠拢，最终紧挨在一起', 0, 110, 42, F_BODY, NAVY, a3)
    a4 = a * smooth((t - 110.0) / 0.5)
    pill(ctx, '又称「最小差异化原理」', 0, 210, 36, F_BODY, CREAM, MINT_D, a4, scale=back_out((t - 110.0) / 0.4),
         shadow=False)
    ctx.restore()


def compare_card(ctx, t):
    a = win(t, 101.0, 106.3, 0.4, 0.4)
    if a <= 0:
        return
    k = max(back_out((t - 101.0) / 0.5), 1e-3)
    ctx.save()
    ctx.translate(W / 2, 250)
    ctx.scale(k, k)
    cw, ch = 860, 200
    rrect(ctx, -cw / 2 + 6, -ch / 2 + 8, cw, ch, 26)
    fill(ctx, NAVY, 0.25 * a)
    rrect(ctx, -cw / 2, -ch / 2, cw, ch, 26)
    fill(ctx, CREAM, a)
    text(ctx, '游客平均步行', 0, -64, 30, F_BODY, NAVY, a * 0.8)
    text(ctx, '最优停法', -230, -14, 30, F_BODY, MINT_D, a)
    text(ctx, '125 m', -230, 42, 60, F_NUM, MINT_D, a)
    text(ctx, '竞争结果', 230, -14, 30, F_BODY, RED, a)
    v = 125 + 125 * ease_out((t - 101.6) / 1.2)
    text(ctx, f'{int(v)} m', 230, 42, 60, F_NUM, RED, a)
    text(ctx, '→', 0, 20, 70, F_NUM, NAVY, a)
    ctx.restore()


def share_at(t):
    a, b = A(t), B(t)
    return clamp(((a + b) / 2) / 1000)


def end_card(ctx, t):
    a = smooth((t - 155.8) / 0.6)
    if a <= 0:
        return
    k = max(back_out((t - 155.8) / 0.6), 1e-3)
    ctx.rectangle(0, 0, W, H)
    fill(ctx, hexc('#3A2547'), 0.35 * a)
    ctx.save()
    ctx.translate(W / 2, 380)
    ctx.scale(k, k)
    text(ctx, '霍特林定律', 0, 0, 150, F_TITLE, CREAM, a, stroke=10, stroke_color=tuple(NAVY), shadow=8)
    ctx.restore()
    a2 = smooth((t - 156.6) / 0.5)
    pill(ctx, '为什么两家奶茶店总开在隔壁', W / 2, 545, 42, F_BODY, CREAM, CORAL_D, a2, padx=32, pady=14)


# ------------------------------------------------------------------ main compositor
def scene_at(t):
    if t < 3.25:
        return 'street_hook'
    if t < 118.0:
        return 'beach'
    if t < 127.3:
        return 'street'
    if t < 138.3:
        return 'voters'
    if t < 148.0:
        return 'phones'
    return 'end'


def draw(ctx, t):
    sc = scene_at(t)
    S = None
    if sc == 'street_hook':
        St.draw_street(ctx, t, 960, lerp(1.0, 1.08, ease_out(t / 3.2)), queue=1.0)
        hook_title(ctx, t)
    elif sc == 'beach':
        cam = (CAM_X(t), CAM_Y(t), CAM_Z(t))
        S = draw_beach(ctx, t, cam)
        sb = smooth((t - 3.5) / 0.5) * (1 - smooth((t - 6.2) / 0.3)) if t < 7 else smooth((t - 25.0) / 0.6) * (
            1 - smooth((t - 105.8) / 0.4))
        scoreboard(ctx, t, share_at(t), sb)
        if 94.4 < t < 100.2:
            stamp(ctx, t, 94.5, '纳什均衡', 'NASH EQUILIBRIUM')
        compare_card(ctx, t)
        if 6.2 < t < 7.0:
            a = win(t, 6.2, 7.0, 0.1, 0.15)
            for k in range(2):
                ctx.move_to(150 + k * 40, 100)
                ctx.line_to(190 + k * 40, 76)
                ctx.line_to(190 + k * 40, 124)
                ctx.close_path()
                fill(ctx, CREAM, a)
            text(ctx, '倒带', 250, 100, 54, F_TITLE, CREAM, a, anchor='l', stroke=6, stroke_color=tuple(NAVY))
        law_card(ctx, t)
    elif sc == 'street':
        k = ease_io((t - 118.0) / 8.4)
        St.draw_street(ctx, t, lerp(1000, 3200, k), lerp(1.0, 0.8, ease_io((t - 118.0) / 3.0)), queue=1.0,
                       pairs_lab=smooth((t - 119.5) / 0.6))
    elif sc == 'voters':
        lt = t - 127.3
        pa = lerp(0.18, 0.47, ease_io((lt - 2.2) / 6.0))
        pb = lerp(0.82, 0.53, ease_io((lt - 2.6) / 6.0))
        share = St.draw_voters(ctx, t, pa, pb, ease_out(lt / 1.6))
        pill(ctx, '中间选民定理', W / 2, 72, 48, F_TITLE, CREAM, NAVY, smooth((lt - 1.0) / 0.5),
             scale=back_out((lt - 1.0) / 0.4))
    elif sc == 'phones':
        lt = t - 138.3
        St.paper(ctx)
        p = ease_io((lt - 1.4) / 4.0)
        for i in range(5):
            x = lerp(260, 1660, i / 4)
            St.phone(ctx, x, 470 + 10 * math.sin(t * 1.5 + i), p, i, smooth(lt / 0.5 - i * 0.12))
        yrs = '2005', '2025'
        text(ctx, yrs[0] if p < 0.5 else yrs[1], W / 2, 130, 70, F_NUM, NAVY, 0.85, scale=1 + 0.1 * math.sin(p * math.pi))
    else:
        z = CAM_END(t)
        S = draw_beach(ctx, t, (960, lerp(612, 560, (z - 1.9) / -0.9), z))
        end_card(ctx, t)
    caption(ctx, t)
    wipe(ctx, t)
    return sc


# ------------------------------------------------------------------ post: grade, vignette, grain
_rng = np.random.default_rng(3)
GRAIN = [(_rng.standard_normal((H // 2, W // 2)).astype(np.float32) * 5.0) for _ in range(6)]
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
VIG = (1 - 0.22 * (((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H / 2) / (H * 0.62)) ** 2) ** 1.5).clip(0.6, 1)[..., None]
GRAD_Y = (yy / H)[..., None]


def post(arr, t, sc):
    img = arr.astype(np.float32)
    if sc in ('beach', 'end'):
        d = DAY(t)
        if d > 0.8:     # sunset
            k = smooth((d - 0.8) / 0.17)
            top = np.array([255, 150, 120], np.float32) / 255
            bot = np.array([255, 205, 160], np.float32) / 255
            mult = (top * (1 - GRAD_Y) + bot * GRAD_Y)
            img = img * (1 - k * 0.4 + k * 0.4 * mult * 1.1)
            img += k * np.array([12, 2, 14], np.float32)
        elif d < 0.4:   # soft morning
            k = (0.4 - d) / 0.3
            img = img * (1 - 0.06 * k) + k * np.array([4, 8, 14], np.float32)
    img *= VIG
    g = GRAIN[int(t * 30) % len(GRAIN)]
    g = np.repeat(np.repeat(g, 2, 0), 2, 1)[..., None]
    img += g
    return np.clip(img, 0, 255).astype(np.uint8)


def frame(t):
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    ctx = cairo.Context(surf)
    sc = draw(ctx, t)
    surf.flush()
    arr = np.ndarray((H, W, 4), np.uint8, surf.get_data())[..., [2, 1, 0]]
    return post(arr, t, sc)
