"""TEMPLATE scenes.py - copy into a new project, then replace EVERYTHING visual with this video's own style.
Contract used by vk_render: TOTAL, render_frame(t, idx). Audio cues are collected per section (see audio.py template).
"""
import math, bisect
import numpy as np
from vk_core import *          # Canvas, add_text, finish, easing, effects ...

# ---- this video's style decisions (fill these from the look-dev step; never copy a previous project's) ----
BG_TOP, BG_BOT = (0.05, 0.06, 0.10), (0.12, 0.10, 0.16)
KEY = (0.40, 0.85, 1.0)
set_tags({'k': KEY, 'h': HILITE, 'd': DIMC})
# set_fonts(lat='C:/Windows/Fonts/bahnschrift.ttf')     # pick a type pairing that fits the topic


def cap(cv, t, t0, t1, text, y=H - 102, size=50, **kw):
    """bottom caption with fade window; t-t0 drives the per-character rise animation"""
    a = win(t, t0, t1, 0.2, 0.3)
    if a > 0:
        add_text(cv, text, W / 2, y, size=size, alpha=a, t=t - t0, **kw)


def stamp(cv, t, t0, t1, text, x, y, size, **kw):
    """title that slams in (scale 1.35 -> 1). a0 = alpha at the very first frame: keep it high for the hook
    (a title that fades in from 0 makes frame 0 empty - the cover frame / first impression)."""
    if t0 <= t <= t1:
        k = ease_out((t - t0) / 0.28)
        a0 = kw.pop('a0', 0.0)
        add_text(cv, text, x, y, size=size, alpha=min(1, a0 + (t - t0) / 0.12) * win(t, t0, t1, 0, 0.4), anim=None,
                 scale=1 + 0.35 * (1 - k), **kw)


def background(cv):
    import cairo
    lg = cairo.LinearGradient(0, 0, 0, H)
    lg.add_color_stop_rgb(0, *BG_TOP)
    lg.add_color_stop_rgb(1, *BG_BOT)
    cv.c.set_source(lg)
    cv.c.paint()


class Section:
    name, dur, cues = '', 1.0, []      # cues: [(local_t, sfx_name, gain, pan)]

    def draw(self, cv, t):
        pass


class Hook(Section):
    """first frame must already be striking: title + motion + sound at t=0"""
    name, dur = 'hook', 4.0
    cues = [(0.0, 'boom', 0.9, 0.0), (0.05, 'whoosh_in', 0.6, 0.0), (1.2, 'impact', 0.8, 0.3)]

    def draw(self, cv, t):
        cv.set_cam(kf_zoom(t), W / 2, H / 2)
        background(cv)
        for i in range(5):
            p0 = (200 + i * 300, 900)
            tracer(cv, p0, (p0[0] + 300, 200), (t * 0.6 + i * 0.17) % 1.2, KEY, width=5)
        dust_motes(cv, t, n=60, col=KEY, alpha=0.4)
        cv.reset_cam()
        stamp(cv, t, 0.0, 4.0, '一个[k]反直觉[/]的问题？', W / 2, 200, 96, glow=0.2, a0=1.0)
        cap(cv, t, 1.0, 4.0, '模板：替换成你的钩子', size=48)
        cv.flash = 0.15 * math.exp(-t * 6)   # keep frame-0 flash small: frame 0 must stay readable


def kf_zoom(t):
    return 1.08 - 0.08 * ease_out(t / 3)


SECTIONS = [Hook()]
STARTS = list(np.cumsum([0] + [s.dur for s in SECTIONS])[:-1])
TOTAL = float(sum(s.dur for s in SECTIONS))


def locate(t):
    i = max(0, bisect.bisect_right(STARTS, t) - 1)
    return SECTIONS[i], t - STARTS[i]


def all_cues():
    return [(t0 + tl, n, g, p) for s, t0 in zip(SECTIONS, STARTS) for (tl, n, g, p) in s.cues]


def render_frame(t, idx=0):
    sec, tl = locate(t)
    cv = Canvas()
    sec.draw(cv, tl)
    return finish(cv, idx)
