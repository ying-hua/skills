"""vk_audio - numpy/scipy sound kit for procedural videos (48 kHz mono building blocks, stereo bus).

Building blocks : tt, noise, env, sweep, filt, P (pad-sum different lengths), norm, bandsweep (moving bandpass)
Spaces          : reverb(x, d) (stereo IR convolution), echo(x, taps) (canyon/slap), pingpong
SFX (~35)       : gunshot, gunshot_small, boom, impact, thud, stomp, ricochet, whoosh, whoosh_in, riser, riser_short,
                  rewind, pop, tick, tick_run, chime (cha-ching), bell_hit, hammer, click, spin, lock, deny, braam,
                  stamp, mystery, hit_soft, cloth, heartbeat, whistle_up, split, merge, computer, wind, flow_bed,
                  sparkle, glitch, geiger
Instruments     : fm_bell, pluck (Karplus-Strong), supersaw, pad, kick, snare, hat, sub, marimba, epiano
Music helpers   : mtof, beat grid via BPM; seq(notes, fn) to lay notes on a bus
Mixing          : Bus (stereo, constant-power pan), cue list -> bus, click_rain(events), load_bgm, duck, master

Every generator returns a float64 mono array normalised to a sensible peak. Tune gain at placement time.
Style is yours: choose instruments/scale/BPM per video; avoid reusing a previous project's palette.
"""
import functools, subprocess
import numpy as np
from scipy.signal import butter, sosfilt, fftconvolve, lfilter

SR = 48000
rng = np.random.default_rng(11)


# ---------------------------------------------------------------- blocks
def tt(d):
    return np.arange(int(d * SR)) / SR


def noise(d):
    return rng.standard_normal(int(d * SR))


def env(d, a=0.002, decay=8.0):
    e = np.exp(-tt(d) * decay)
    na = max(1, int(a * SR))
    e[:na] *= np.linspace(0, 1, min(na, len(e)))
    return e


def adsr(d, a=0.01, dcy=0.1, s=0.7, r=0.2):
    n = int(d * SR)
    e = np.full(n, s)
    na = min(int(a * SR), n)
    nd = min(int(dcy * SR), n - na)
    nr = min(int(r * SR), n)
    e[:na] = np.linspace(0, 1, na)
    e[na:na + nd] = np.linspace(1, s, len(e[na:na + nd]))
    if nr:
        e[-nr:] *= np.linspace(1, 0, nr)
    return e


def sweep(f0, f1, d, curve='exp'):
    t = tt(d)
    f = f0 * (f1 / f0) ** (t / d) if curve == 'exp' else f0 + (f1 - f0) * t / d
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


def filt(x, kind, f, order=2):
    return sosfilt(butter(order, f, kind, fs=SR, output='sos'), x)


def P(*xs):
    """sum arrays of different lengths (avoids the classic broadcast error)"""
    out = np.zeros(max(len(x) for x in xs))
    for x in xs:
        out[:len(x)] += x
    return out


def norm(x, g=1.0):
    return x / (np.abs(x).max() + 1e-9) * g


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def bandsweep(d, f0, f1, q=0.6):
    """noise through a bandpass whose centre glides f0->f1 (block-wise)"""
    n = noise(d + 0.05)
    out = np.zeros(int(d * SR))
    seg = 512
    for i in range(0, len(out), seg):
        fc = f0 * (f1 / f0) ** (i / len(out))
        lo, hi = max(20, fc * (1 - q)), min(fc * (1 + q * 1.6), SR / 2 - 100)
        blk = filt(n[i:i + seg + 2048], 'band', [lo, hi])
        out[i:i + seg] = blk[:len(out[i:i + seg])]
    return out


# ---------------------------------------------------------------- spaces
@functools.lru_cache(8)
def _ir(d, seed, bright):
    r = np.random.default_rng(seed)
    t = tt(d)
    irs = []
    for _ in range(2):
        x = r.standard_normal(len(t)) * np.exp(-t * 6.9 / d)
        x = filt(x, 'low', bright)
        x[:int(0.012 * SR)] = 0
        irs.append(x / np.sqrt((x ** 2).sum()))
    return np.stack(irs, 1)


def reverb(x, d=2.4, wet=0.3, bright=5000, seed=0):
    """mono or stereo in -> stereo out (len + d)"""
    ir = _ir(d, seed, bright)
    xs = np.stack([x, x], 1) if x.ndim == 1 else x
    out = np.zeros((len(xs) + len(ir) - 1, 2))
    for c in range(2):
        out[:, c] = fftconvolve(xs[:, c], ir[:, c]) * wet
    out[:len(xs)] += xs * (1 - wet)
    return out


def echo(x, taps=((0.28, 0.35), (0.61, 0.22), (1.05, 0.12), (1.6, 0.06)), lp=2200):
    """discrete slap echoes (canyon / hall). Mono."""
    out = np.zeros(len(x) + int((taps[-1][0] + 0.1) * SR))
    out[:len(x)] += x
    l = filt(x, 'low', lp)
    for d, g in taps:
        i = int(d * SR)
        out[i:i + len(x)] += l * g
    return out


def pingpong(x, delay=0.375, fb=0.45, n=6):
    out = np.zeros((len(x) + int(delay * SR * n), 2))
    g = 1.0
    for k in range(n):
        i = int(k * delay * SR)
        out[i:i + len(x), k % 2] += x * g
        g *= fb
    return out


# ---------------------------------------------------------------- SFX
def gunshot(big=1.0, room=True):
    crack = filt(noise(0.06), 'high', 1500) * env(0.06, 0.0005, 70)
    body = filt(noise(0.9), 'low', 1800) * env(0.9, 0.001, 9)
    thump = sweep(140, 45, 0.35) * env(0.35, 0.001, 9)
    x = np.tanh(P(crack * 1.2, body * 0.8, thump * 1.1 * big) * 2.5)
    return norm(echo(x) if room else x)


def gunshot_small():
    x = filt(noise(0.25), 'band', [800, 5000]) * env(0.25, 0.0005, 30)
    return norm(echo(x, ((0.2, 0.25), (0.45, 0.1))), 0.8)


def boom(d=2.6):
    x = P(sweep(70, 28, d) * env(d, 0.01, 1.6), filt(noise(d), 'low', 300) * env(d, 0.005, 2.0) * 0.6,
          filt(noise(d), 'band', [200, 900]) * env(d, 0.3, 2.5) * 0.25)
    return norm(x)


def impact():
    return norm(P(filt(noise(0.4), 'low', 900) * env(0.4, 0.001, 18), sweep(110, 50, 0.2) * env(0.2, 0.001, 20),
                  filt(noise(0.4), 'band', [2000, 6000]) * env(0.4, 0.001, 25) * 0.4), 0.9)


def thud():
    return norm(P(sweep(90, 40, 0.6) * env(0.6, 0.002, 12), filt(noise(0.6), 'low', 400) * env(0.6, 0.002, 10) * 0.7,
                  filt(noise(0.8), 'band', [1500, 5000]) * env(0.8, 0.05, 5) * 0.15), 0.9)


def stomp():
    return norm(P(thud() * 0.8, impact() * 0.4), 0.8)


def ricochet(d=0.7):
    f0 = rng.uniform(2600, 3400)
    x = P(sweep(f0, f0 * 0.45, d) * env(d, 0.002, 4.5), filt(noise(0.05), 'high', 2000) * env(0.05, 0.0005, 60) * 0.5)
    return norm(echo(x * 0.8, ((0.3, 0.2),)), 0.6)


def whoosh(d=0.6, f0=300, f1=3000):
    e = np.sin(np.pi * np.clip(tt(d) / d, 0, 1)) ** 2
    return norm(bandsweep(d, f0, f1) * e, 0.7)


def whoosh_in():
    return whoosh(0.35, 3000, 400)


def riser(d=2.0):
    n = int(d * SR)
    return norm(P(whoosh(d, 200, 6000) * np.linspace(0.2, 1, n), sweep(110, 440, d) * np.linspace(0, 0.25, n)), 0.6)


def riser_short():
    return riser(0.9)


def rewind():
    d = 0.8
    x = P(sweep(1800, 300, d) * 0.3, whoosh(d, 4000, 300) * 0.8)
    return norm(x * (0.6 + 0.4 * np.sin(2 * np.pi * 26 * tt(d))) * env(d, 0.02, 1.5), 0.7)


def pop():
    d = 0.12
    return norm(P(sweep(900, 1500, d) * env(d, 0.001, 35), filt(noise(d), 'high', 4000) * env(d, 0.0005, 80) * 0.3), 0.6)


def tick():
    return norm(filt(noise(0.03), 'band', [3000, 8000]) * env(0.03, 0.0003, 200), 0.5)


def tick_run(d=1.6):
    """accelerating ticks (number counting up)"""
    out = np.zeros(int((d + 0.1) * SR))
    t, k = 0.0, 0
    while t < d:
        i = int(t * SR)
        x = tick() * (0.6 + 0.4 * (k % 2))
        out[i:i + len(x)] += x
        t += 0.045 + 0.06 * (t / d) ** 2
        k += 1
    return out


def chime(notes=(1568, 2093, 2637), gap=0.07, d=1.4):
    out = np.zeros(int(d * SR))
    for j, f in enumerate(notes):
        i = int(j * gap * SR)
        b = (np.sin(2 * np.pi * f * tt(d)) + 0.4 * np.sin(2 * np.pi * f * 2.76 * tt(d))) * env(d, 0.001, 4)
        m = min(len(b), len(out) - i)
        out[i:i + m] += b[:m]
    return norm(out, 0.55)


def bell_hit(f=440, d=2.5):
    return norm(sum(a * np.sin(2 * np.pi * f * r * tt(d)) * env(d, 0.001, 1.5 * r)
                    for r, a in ((1, 1), (2.4, 0.5), (3.9, 0.3), (5.4, 0.2))), 0.5)


def click():
    return norm(filt(noise(0.03), 'band', [1200, 6000]) * env(0.03, 0.0003, 150), 0.6)


def hammer():
    a = filt(noise(0.04), 'band', [1500, 7000]) * env(0.04, 0.0003, 120)
    b = filt(noise(0.05), 'band', [800, 5000]) * env(0.05, 0.0003, 90)
    x = np.zeros(int(0.3 * SR))
    x[:len(a)] += a
    i = int(0.11 * SR)
    x[i:i + len(b)] += b * 1.3
    return norm(x, 0.8)


def spin(d=1.0):
    """decelerating ratchet (revolver cylinder, dial, wheel)"""
    out = np.zeros(int((d + 0.1) * SR))
    t = 0.0
    while t < d:
        c = click() * (0.5 + 0.5 * (1 - t / d))
        i = int(t * SR)
        out[i:i + len(c)] += c
        t += 0.035 + 0.12 * (t / d) ** 2
    return out * 0.8


def lock():
    a = sweep(1800, 2400, 0.08) * env(0.08, 0.001, 30)
    b = np.sin(2 * np.pi * 2400 * tt(0.35)) * env(0.35, 0.001, 14) * 0.6
    x = np.zeros(int(0.45 * SR))
    x[:len(a)] += a
    i = int(0.09 * SR)
    x[i:i + len(b)] += b
    return norm(P(x, click() * 0.6), 0.5)


def deny():
    x = np.sign(np.sin(2 * np.pi * 120 * tt(0.4))) * env(0.4, 0.005, 6)
    return norm(filt(x, 'low', 1200), 0.5)


def braam(d=3.0, root=55.0):
    t = tt(d)
    x = sum(np.sign(np.sin(2 * np.pi * f * t + p)) for f, p in
            ((root, 0), (root * 1.007, 1), (root * 1.498, 2), (root * 2.005, 0.5)))
    return norm(np.tanh(filt(x, 'low', 700) * env(d, 0.03, 1.1) * 1.5), 0.8)


def stamp():
    return norm(P(impact() * 0.7, pop() * 0.5), 0.7)


def mystery(d=3.5, freqs=(311.1, 370.0, 466.2, 554.4)):
    x = sum(np.sin(2 * np.pi * f * tt(d)) * env(d, 0.6, 0.8) for f in freqs)
    return norm(x * (0.7 + 0.3 * np.sin(2 * np.pi * 5 * tt(d))), 0.35)


def hit_soft(d=2.0):
    return norm(P(sweep(60, 40, d) * env(d, 0.005, 2.5), filt(noise(d), 'low', 200) * env(d, 0.005, 3) * 0.3), 0.8)


def cloth():
    return norm(filt(noise(0.5), 'band', [500, 3000]) * np.sin(np.pi * tt(0.5) / 0.5) ** 2, 0.3)


def heartbeat(n=3, period=0.9):
    beat = sweep(70, 45, 0.18) * env(0.18, 0.004, 22)
    out = np.zeros(int((n * period + 1) * SR))
    for k in range(n):
        for dl, g in ((0, 1.0), (0.22, 0.7)):
            i = int((k * period + dl) * SR)
            out[i:i + len(beat)] += beat * g
    return norm(out, 0.9)


def whistle_up(d=1.6):
    return norm(P(sweep(1200, 3200, d) * env(d, 0.01, 1.8) * 0.5, whoosh(d, 1500, 8000) * 0.3), 0.45)


def split():
    return norm(P(whoosh(0.6, 400, 2500) * 0.6, np.sin(2 * np.pi * 660 * tt(0.6)) * env(0.6, 0.005, 7) * 0.3), 0.5)


def merge(d=1.8, freqs=(220, 277.2, 329.6, 440)):
    return norm(P(sum(np.sin(2 * np.pi * f * tt(d)) * env(d, 0.3, 1.2) for f in freqs), whoosh(d, 200, 2000) * 0.5), 0.55)


def computer(n=14, step=0.1):
    out = np.zeros(int((n * step + 0.2) * SR))
    for k in range(n):
        f = rng.choice([880, 1175, 1320, 1760, 2093])
        b = np.sign(np.sin(2 * np.pi * f * tt(0.06))) * env(0.06, 0.001, 30) * 0.3
        i = int(k * step * SR)
        out[i:i + len(b)] += b
    return filt(out, 'low', 5000)


def wind(d=8.0):
    t = tt(d)
    mod = 0.5 + 0.35 * np.sin(2 * np.pi * 0.17 * t) + 0.15 * np.sin(2 * np.pi * 0.43 * t + 2)
    e = np.minimum(1, t / 0.05) * np.minimum(1, (d - t) / 2.5)
    return norm((filt(noise(d), 'band', [200, 1400]) * mod + sweep(700, 900, d) * 0.04 * mod) * e, 0.35)


def flow_bed(d=30.0):
    """soft moving noise bed (rivers, particles, data streams)"""
    t = tt(d)
    mod = 0.5 + 0.5 * np.sin(2 * np.pi * 0.23 * t) * np.sin(2 * np.pi * 0.11 * t + 1)
    e = np.minimum(1, t / 2) * np.minimum(1, (d - t) / 2)
    return norm(filt(noise(d), 'band', [300, 2500]) * (0.3 + 0.3 * mod) * e, 0.18)


def sparkle(d=1.2, n=18):
    out = np.zeros(int(d * SR))
    for k in range(n):
        f = rng.uniform(3000, 7000)
        b = np.sin(2 * np.pi * f * tt(0.15)) * env(0.15, 0.001, 30)
        i = int(rng.uniform(0, d - 0.15) * SR)
        out[i:i + len(b)] += b * rng.uniform(0.3, 1)
    return norm(out, 0.4)


def glitch(d=0.4):
    x = np.repeat(rng.standard_normal(int(d * SR) // 300 + 1), 300)[:int(d * SR)]
    x *= np.sign(np.sin(2 * np.pi * rng.uniform(60, 400) * tt(d)))
    return norm(filt(x, 'band', [300, 6000]) * (rng.random(len(x)) > 0.2), 0.5)


def geiger(rate=8.0, d=2.0):
    out = np.zeros(int(d * SR))
    for ti in np.cumsum(rng.exponential(1 / rate, int(rate * d * 3))):
        if ti >= d - 0.01:
            break
        c = click()
        i = int(ti * SR)
        out[i:i + len(c)] += c[:len(out) - i]
    return out


# ---------------------------------------------------------------- instruments
def fm_bell(f, d=3.0, ratio=3.5, index=3.0, vel=1.0):
    t = tt(d)
    I = index * np.exp(-t * 2.5)
    x = np.sin(2 * np.pi * f * t + I * np.sin(2 * np.pi * f * ratio * t)) * env(d, 0.002, 1.6)
    x += 0.3 * np.sin(2 * np.pi * f * 2.76 * t) * env(d, 0.001, 4)
    return x * vel * 0.5


def pluck(f, d=1.5, decay=0.996, bright=0.5, vel=1.0):
    """Karplus-Strong"""
    L = max(2, int(SR / f))
    burst = filt(noise(L / SR + 0.001), 'low', 2000 + 8000 * bright)[:L]
    n = int(d * SR)
    x = np.zeros(n)
    x[:L] = burst
    b = np.zeros(L + 2)
    b[0] = 1.0
    a = np.zeros(L + 2)
    a[0] = 1.0
    a[L] = -decay * 0.5
    a[L + 1] = -decay * 0.5
    y = lfilter([1.0], a, x)
    return norm(y, vel * 0.6)


def supersaw(f, d, n=5, detune=0.012, cut=2500, vel=1.0, a=0.3, r=0.6):
    t = tt(d)
    x = sum((2 * ((f * (1 + detune * (k - n // 2) / (n // 2 or 1)) * t + rng.random()) % 1) - 1) for k in range(n))
    return filt(x / n, 'low', cut) * adsr(d, a, 0.2, 0.8, r) * vel


def pad(notes, d, bright=1500, vel=1.0):
    t = tt(d)
    x = np.zeros(len(t))
    for m in notes:
        f = mtof(m)
        for h in range(1, 7):
            for det in (-0.004, 0.004):
                x += np.sin(2 * np.pi * f * h * (1 + det) * t + h) / h ** 1.3
    lfo = 0.75 + 0.25 * np.sin(2 * np.pi * 0.2 * t)
    return filt(x * lfo, 'low', bright) * adsr(d, min(1.0, d / 4), 0.3, 0.9, min(1.5, d / 3)) * vel / (len(notes) * 4)


def kick(vel=1.0):
    d = 0.5
    return norm(P(sweep(160, 42, d) * env(d, 0.001, 7), filt(noise(0.01), 'high', 3000) * 0.3), vel)


def snare(vel=1.0):
    d = 0.3
    return norm(P(filt(noise(d), 'band', [1500, 8000]) * env(d, 0.001, 18), np.sin(2 * np.pi * 190 * tt(0.1)) * env(0.1, 0.001, 30) * 0.6), vel * 0.8)


def hat(vel=1.0, open_=False):
    d = 0.35 if open_ else 0.06
    return norm(filt(noise(d), 'high', 7000) * env(d, 0.0005, 8 if open_ else 60), vel * 0.4)


def sub(f, d, vel=1.0):
    return np.sin(2 * np.pi * f * tt(d)) * adsr(d, 0.02, 0.1, 0.9, 0.1) * vel


def marimba(f, d=1.2, vel=1.0):
    t = tt(d)
    return (np.sin(2 * np.pi * f * t) * env(d, 0.001, 5) + 0.35 * np.sin(2 * np.pi * f * 3.93 * t) * env(d, 0.001, 18)
            + 0.15 * np.sin(2 * np.pi * f * 9.2 * t) * env(d, 0.001, 40)) * vel * 0.5


def epiano(f, d=2.0, vel=1.0):
    t = tt(d)
    I = 1.6 * np.exp(-t * 3)
    return np.sin(2 * np.pi * f * t + I * np.sin(2 * np.pi * f * t)) * env(d, 0.003, 1.8) * vel * 0.5


# ---------------------------------------------------------------- mixing
class Bus:
    def __init__(self, total_sec):
        self.x = np.zeros((int(total_sec * SR) + SR, 2))

    def add(self, sig, t, gain=1.0, pan=0.0):
        i = int(t * SR)
        if i >= len(self.x) or gain == 0:
            return
        if i < 0:
            sig = sig[-i:]
            i = 0
        n = min(len(sig), len(self.x) - i)
        if sig.ndim == 1:
            l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
            self.x[i:i + n, 0] += sig[:n] * gain * l * 1.414
            self.x[i:i + n, 1] += sig[:n] * gain * r * 1.414
        else:
            self.x[i:i + n] += sig[:n] * gain


def render_cues(bus, cues, lib=None):
    """cues: [(t, name_or_callable, gain, pan)]; names resolve to functions in this module or `lib` dict"""
    g = globals()
    cache = {}
    for t, name, gain, pan in cues:
        if callable(name):
            sig = name()
        else:
            if name not in cache:
                fn = (lib or {}).get(name) or g.get(name)
                if fn is None:
                    raise KeyError(f'unknown sfx {name!r}')
                cache[name] = fn
            sig = cache[name]()
        bus.add(sig, t, gain, pan)


def click_rain(bus, events, base_gain=0.08, dens_ref=300.0, span=None):
    """events: [(t, strength 0..1, pan)] - e.g. every simulated particle hit / shot. Gain shrinks with density."""
    clicks = [filt(noise(0.02), 'band', [1500 + 800 * k, 7000]) * env(0.02, 0.0002, 260) for k in range(4)]
    if span is None and events:
        span = max(1e-3, max(e[0] for e in events) - min(e[0] for e in events))
    dens = len(events) / span if events else 1
    g0 = base_gain / max(1.0, (dens / dens_ref) ** 0.5)
    for j, (t, s, pan) in enumerate(events):
        bus.add(clicks[j % 4], t, g0 * (0.5 + s), pan)


def load_bgm(path, total_sec):
    p = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', path, '-ar', str(SR), '-ac', '2', '-f', 's16le', '-'],
                       capture_output=True)
    b = np.frombuffer(p.stdout, np.int16).reshape(-1, 2).astype(np.float64) / 32768
    out = np.zeros((int(total_sec * SR) + SR, 2))
    n = min(len(out), len(b))
    out[:n] = b[:n]
    return out


def duck(music, sfx, amount=1.2, speed_hz=3.0):
    """sidechain: lower music under loud sfx"""
    lvl = np.abs(sfx).max(1)
    w = int(0.05 * SR)
    lv = np.convolve(lvl, np.ones(w) / w, 'same')
    sm = sosfilt(butter(1, speed_hz, 'low', fs=SR, output='sos'), lv)
    return music * (1 / (1 + amount * np.clip(sm, 0, 2)))[:, None]


def master(mix, total_sec, path, fade_out=1.3, drive=1.25):
    """soft-clip master -> 16-bit wav (final LUFS is set later by vk_finalize loudnorm)"""
    from scipy.io import wavfile
    mix = mix[:int(total_sec * SR)].copy()
    mix -= mix.mean(0)
    mix = filt(mix.T, 'high', 25).T if mix.ndim == 2 else filt(mix, 'high', 25)
    fo = min(int(fade_out * SR), len(mix))
    if fo:
        mix[-fo:] *= np.linspace(1, 0, fo)[:, None]
    pk = np.abs(mix).max()
    mix = np.tanh(mix / max(pk, 1e-9) * drive) / np.tanh(drive) * 0.93
    wavfile.write(path, SR, (mix * 32767).astype(np.int16))
    print('wrote', path, 'rms dB', round(20 * np.log10(np.sqrt((mix ** 2).mean())), 1))
