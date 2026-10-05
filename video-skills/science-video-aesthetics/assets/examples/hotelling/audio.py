"""Synthesised SFX + ambience, mixed under bgm.mp3 -> out/audio.wav"""
import subprocess
import numpy as np
from scipy import signal
from scipy.io import wavfile
import story
from story import A, B, DUR, CAPS, DELTAS, BUBBLES, WIPES, MOVES, PEOPLE
from world import m2x, choice

SR = 48000
N = int(DUR * SR)
L = np.zeros(N)
R = np.zeros(N)
rng = np.random.default_rng(5)


def env(n, a=0.005, d=0.2):
    t = np.arange(n) / SR
    return np.minimum(1, t / a) * np.exp(-t / d)


def add(t, x, gain=1.0, pan=0.0):
    i = int(t * SR)
    if i >= N or i + len(x) <= 0:
        return
    x = x[:N - i] * gain
    gl, gr = np.sqrt(0.5 * (1 - pan)), np.sqrt(0.5 * (1 + pan))
    L[i:i + len(x)] += x * gl
    R[i:i + len(x)] += x * gr


def bp(x, lo, hi, order=2):
    sos = signal.butter(order, [lo, hi], 'band', fs=SR, output='sos')
    return signal.sosfilt(sos, x)


def lp(x, f, order=2):
    return signal.sosfilt(signal.butter(order, f, 'low', fs=SR, output='sos'), x)


def tone(f, dur, d=0.2, a=0.003, harm=((1, 1),)):
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = sum(g * np.sin(2 * np.pi * f * h * t) for h, g in harm)
    return y * env(n, a, d)


def pop(pitch=1.0):
    n = int(0.12 * SR)
    t = np.arange(n) / SR
    f = 700 * pitch * np.exp(-t * 18) + 380 * pitch
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.002, 0.035)


def whoosh(dur=0.8):
    n = int(dur * SR)
    x = rng.standard_normal(n)
    t = np.linspace(0, 1, n)
    lo, hi = bp(x, 200, 900), bp(x, 1500, 6000)
    k = np.sin(np.pi * t) ** 2
    return (lo * (1 - k) + hi * k * 0.8 + lo * 0.5) * k * 1.4


def kaching():
    y = tone(2093, 0.9, 0.35, harm=((1, 1), (2.76, 0.4), (5.4, 0.2))) + tone(2637, 0.9, 0.3, harm=((1, .8),))
    y2 = np.concatenate([np.zeros(int(0.07 * SR)), y])
    clank = bp(rng.standard_normal(int(0.05 * SR)), 2000, 7000) * env(int(0.05 * SR), 0.001, 0.015)
    out = np.zeros(len(y2))
    out[:len(clank)] += clank * 1.5
    out[:len(y)] += y * 0.5
    out += y2 * 0.5
    return out


def buzz():
    n = int(0.55 * SR)
    t = np.arange(n) / SR
    f = 220 - 80 * t
    y = signal.sawtooth(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.01, 0.35)
    return lp(y, 1600) * 0.6


def thunk():
    n = int(0.6 * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * np.cumsum(90 * np.exp(-t * 6) + 45) / SR) * env(n, 0.002, 0.18)
    y += bp(rng.standard_normal(n), 200, 2500) * env(n, 0.001, 0.03) * 0.8
    return y


def slam():
    y = thunk() * 1.3
    sh = sum(tone(f, 1.6, 0.7, 0.01) for f in (1318, 1568, 1976, 2637)) * 0.12
    out = np.zeros(max(len(y), len(sh)))
    out[:len(y)] += y
    out[:len(sh)] += sh
    return out


def horn(f=440):
    n = int(0.22 * SR)
    t = np.arange(n) / SR
    y = (signal.square(2 * np.pi * f * t, 0.4) * 0.5 + np.sin(2 * np.pi * f * 1.26 * t)) * np.minimum(1, t / 0.01) * np.minimum(1, (n / SR - t) / 0.03)
    y = lp(y, 2500)
    return np.concatenate([y, np.zeros(int(0.06 * SR)), y])


def engine(dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 38 + 10 * np.sin(np.pi * t / dur)
    y = signal.sawtooth(2 * np.pi * np.cumsum(f) / SR) * 0.5
    y = lp(y, 380) + bp(rng.standard_normal(n), 500, 2500) * 0.25   # tyres on sand
    e = np.minimum(1, t / 0.15) * np.minimum(1, (dur - t) / 0.25).clip(0)
    return y * e


def chime(notes, gap=0.11, d=0.6):
    out = np.zeros(int((len(notes) * gap + 2.0) * SR))
    for k, f in enumerate(notes):
        y = tone(f, 2.0, d, 0.003, ((1, 1), (2, 0.25), (3, 0.1)))
        i = int(k * gap * SR)
        out[i:i + len(y)] += y
    return out


def blip():
    return tone(1046, 0.15, 0.05) * 0.6 + tone(1568, 0.15, 0.04) * 0.4


def rewind(dur=0.7):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 600 + 2600 * t / dur + 200 * np.sin(2 * np.pi * 23 * t)
    y = signal.sawtooth(2 * np.pi * np.cumsum(f) / SR) * 0.3 + bp(rng.standard_normal(n), 2000, 6000) * 0.3
    return lp(y, 5000) * np.sin(np.pi * t / dur)


def gull():
    n = int(0.5 * SR)
    t = np.arange(n) / SR
    f = 1500 + 900 * np.sin(np.pi * t / 0.5) - 600 * t
    y = np.sin(2 * np.pi * np.cumsum(f) / SR + 2 * np.sin(2 * np.pi * 30 * t))
    return y * np.sin(np.pi * t / 0.5) ** 2 * 0.25


def pan_of(x):
    return float(np.clip((x - 960) / 960, -0.9, 0.9))


# ---------------------------------------------------------------- ambience
def segment_env(a, b, f=0.6):
    t = np.arange(N) / SR
    return np.clip(np.minimum((t - a) / f, (b - t) / f), 0, 1)


t_all = np.arange(N) / SR
noise = rng.standard_normal((2, N))
surf = np.stack([lp(bp(noise[c], 150, 3000), 1800) for c in range(2)])
p = (t_all / 6.5) % 1.0
swell = 0.35 + 0.65 * np.sin(np.pi * p) ** 2
beach = segment_env(3.25, 118.0, 0.3) + segment_env(148.0, DUR + 1, 0.4)
L += surf[0] * swell * beach * 0.10
R += surf[1] * swell * beach * 0.10
murmur = np.stack([bp(noise[1 - c], 300, 1100) for c in range(2)])
street = segment_env(-1, 3.25, 0.2) + segment_env(118.0, 127.3, 0.3)
L += murmur[0] * street * 0.06 * (1 + 0.3 * np.sin(t_all * 1.3))
R += murmur[1] * street * 0.06 * (1 + 0.3 * np.cos(t_all * 1.1))
for gt in [5.0, 9.5, 27.0, 44.0, 77.0, 103.0, 150.0, 154.5]:
    add(gt, gull(), 0.5, rng.uniform(-0.6, 0.6))
    add(gt + 0.45, gull(), 0.35, rng.uniform(-0.6, 0.6))

# ---------------------------------------------------------------- events
add(0.0, slam(), 0.7)
add(1.2, pop(1.3), 0.5)
for w in WIPES:
    add(w - 0.4, whoosh(0.8), 0.35)
add(3.4, chime([784, 988, 1175, 1568], 0.07, 0.4), 0.18)
add(6.25, rewind(), 0.35)
for a, b, s in CAPS:
    add(a, tone(1800, 0.05, 0.012), 0.06)
for t0, t1, who in MOVES:
    if 7 < t0 < 6.25 or t1 - t0 < 0.3:
        pass
    tr = A if who == 'A' else B
    x = m2x(tr((t0 + t1) / 2))
    add(t0, engine(t1 - t0 + 0.2), 0.28, pan_of(x))
add(15.0, horn(440), 0.22, -0.6)
add(15.5, horn(370), 0.22, 0.6)
add(20.5, pop(1.4), 0.6)
add(20.5, chime([1046, 1318]), 0.1)
# badge pops: reveal wave + flips while trucks move
hlm = PEOPLE[story.HL]['m']
for pp in PEOPLE:
    tr_ = 22.6 + abs(pp['m'] - hlm) / 600
    if tr_ < 25:
        add(tr_, pop(0.9 + pp['m'] / 1000), 0.12, pan_of(pp['x']))
prev = None
for f in range(int(25 * 30), int(118 * 30)):
    t = f / 30
    cur = [choice(pp['m'], A(t), B(t)) for pp in PEOPLE]
    if prev is not None:
        for pp, c0, c1 in zip(PEOPLE, prev, cur):
            if c0 != c1:
                add(t, pop(1.5 if c1 == 'A' else 1.1), 0.22, pan_of(pp['x']))
    prev = cur
for t0, s, col, m in DELTAS:
    if s.startswith('+'):
        add(t0, kaching(), 0.32, pan_of(m2x(m)))
    else:
        add(t0, buzz(), 0.35, pan_of(m2x(m)))
for t0, t1, who, s in BUBBLES:
    add(t0, blip(), 0.35)
add(68.7, thunk(), 0.65)
add(68.75, chime([523, 659, 784]), 0.12)
add(94.5, thunk(), 0.6)
add(94.5, slam(), 0.3)
for k in range(12):
    add(101.6 + k * 0.1, tone(2400, 0.04, 0.01), 0.08)
add(101.0, pop(1.2), 0.4)
add(106.0, chime([523, 659, 784, 1046, 1318], 0.09, 0.8), 0.22)
add(110.0, pop(1.3), 0.4)
add(119.5, chime([880, 1175], 0.08), 0.12)
for k in range(30):
    add(127.3 + k * 0.05, pop(0.8 + k / 30), 0.07)
add(127.3 + 1.0, pop(1.1), 0.4)
add(139.6, whoosh(1.6), 0.25)
add(141.4, chime([1318, 1568, 1976, 2637], 0.06, 0.5), 0.14)
add(155.8, slam(), 0.6)
add(156.0, chime([523, 659, 784, 1046, 1318, 1568], 0.1, 1.0), 0.2)

sfx = np.stack([L, R], 1)
# ---------------------------------------------------------------- bgm
raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', '../bgm.mp3', '-f', 'f32le', '-ac', '2', '-ar', str(SR), '-'],
                     capture_output=True).stdout
bgm = np.frombuffer(raw, np.float32).reshape(-1, 2).astype(np.float64)[:N]
if len(bgm) < N:
    bgm = np.concatenate([bgm, np.zeros((N - len(bgm), 2))])
fade = np.clip((DUR - t_all) / 3.0, 0, 1)[:, None]
mix = bgm * 0.62 * fade + sfx * np.clip((DUR - t_all) / 1.0, 0, 1)[:, None]
pk = np.abs(mix).max()
print('peak', pk)
mix = np.tanh(mix * 1.05) * 0.95
wavfile.write('out/audio.wav', SR, (mix * 32767).astype(np.int16))
print('ok')
