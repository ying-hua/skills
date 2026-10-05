"""Analyse a supplied BGM so section cuts can be locked to its structure without listening.
  python vk_bgm.py ../bgm.mp3
Prints duration, tempo guess, 1 s level curve, HITS (sudden jumps = drops / new sections),
QUIET spans (breakdowns: put the reflective 'aha' beat here), SILENCES (gaps: dramatic pause / final punch).
"""
import subprocess, sys
import numpy as np


def load(path, sr=22050):
    p = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', path, '-ac', '1', '-ar', str(sr), '-f', 's16le', '-'],
                       capture_output=True)
    return np.frombuffer(p.stdout, np.int16).astype(np.float32) / 32768, sr


def analyse(path):
    x, sr = load(path)
    dur = len(x) / sr
    hop = sr // 10
    n = len(x) // hop
    db = np.array([20 * np.log10(np.sqrt((x[i * hop:(i + 1) * hop] ** 2).mean()) + 1e-9) for i in range(n)])
    print(f'duration {dur:.2f}s')
    h2 = 256
    e = np.array([np.sqrt((x[i * h2:(i + 1) * h2] ** 2).mean()) for i in range(len(x) // h2)])
    o = np.maximum(np.diff(np.log(e + 1e-4)), 0)
    fr = sr / h2
    seg = o[:int(min(len(o), 60 * fr))]
    seg = seg - seg.mean()
    ac = np.correlate(seg, seg, 'full')[len(seg) - 1:]
    lags = np.arange(len(ac)) / fr
    m = (lags > 0.33) & (lags < 1.5)
    best = lags[np.argmax(ac * m)]
    print(f'tempo guess {60 / best:.1f} BPM (beat {best:.3f}s; may be half/double)')
    sec = [db[i * 10:(i + 1) * 10].mean() for i in range(int(dur))]
    print('level per second (dB):\n' + ' '.join(f'{i}:{v:.0f}' for i, v in enumerate(sec)))
    med = np.median(db)
    hits = []
    for i in range(5, n):
        if db[i] - db[i - 5:i].mean() >= 8 and db[i] > med - 6 and (not hits or i / 10 - hits[-1] > 2.0):
            hits.append(round(i / 10, 1))
    print('HITS (s):', hits)
    roll = np.convolve(db, np.ones(20) / 20, 'same')
    spans, s0 = [], None
    for i, q in enumerate(roll < med - 2):
        if q and s0 is None:
            s0 = i
        if (not q or i == n - 1) and s0 is not None:
            if (i - s0) / 10 >= 4:
                spans.append((round(s0 / 10, 1), round(i / 10, 1)))
            s0 = None
    print('QUIET spans (s):', spans)
    sil = np.where(db < -30)[0]
    if len(sil):
        groups = np.split(sil, np.where(np.diff(sil) > 1)[0] + 1)
        print("SILENCES (s):", [(float(g[0]) / 10, float(g[-1] + 1) / 10) for g in groups if len(g) >= 3])
    print('Refine any boundary with 0.1 s levels: python -c "import vk_bgm" ... or slice db around it.')


if __name__ == '__main__':
    analyse(sys.argv[1])
