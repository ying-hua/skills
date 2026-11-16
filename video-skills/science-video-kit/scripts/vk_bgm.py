"""Analyse a supplied BGM so section cuts can be locked to its structure without listening.
  python vk_bgm.py ../bgm.mp3
Prints duration, tempo guess, 1 s level curve, HITS (sudden jumps = drops / new sections),
QUIET spans (breakdowns: put the reflective 'aha' beat here), SILENCES (gaps: dramatic pause / final punch),
KEY (best-matching major/minor key + its pentatonic MIDI notes, so tonal SFX - bells, plucks, pads - sit in the
song's key instead of clashing with it).
"""
import subprocess, sys
import numpy as np


def load(path, sr=22050):
    p = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', path, '-ac', '1', '-ar', str(sr), '-f', 's16le', '-'],
                       capture_output=True)
    return np.frombuffer(p.stdout, np.int16).astype(np.float32) / 32768, sr


NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
# Krumhansl-Kessler key profiles (tonic first)
_MAJ = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MIN = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def chroma(x, sr, n=8192, lo=80.0, hi=2000.0):
    """12-bin pitch-class energy of a mono signal (Hann-windowed FFT frames, 80 Hz - 2 kHz)"""
    f = np.fft.rfftfreq(n, 1 / sr)
    m = (f > lo) & (f < hi)
    pc = np.round(69 + 12 * np.log2(f[m] / 440)).astype(int) % 12
    win = np.hanning(n).astype(np.float32)
    out = np.zeros(12)
    for i in range(0, len(x) - n, n):
        X = np.abs(np.fft.rfft(x[i:i + n] * win))[m] ** 2
        out += np.bincount(pc, X, 12)
    return out / max(out.max(), 1e-12)


def key_of(x, sr):
    """-> (tonic pitch class 0..11, 'major'|'minor', correlation, pentatonic MIDI notes in octave 4-5).
    Correlates the chroma with all 24 rotated key profiles; minor pentatonic = 1 b3 4 5 b7, major = 1 2 3 5 6."""
    ch = chroma(x, sr)
    best = (-2.0, 0, 'major')
    for k in range(12):
        for mode, prof in (('major', _MAJ), ('minor', _MIN)):
            r = np.corrcoef(ch, np.roll(prof, k))[0, 1]
            if r > best[0]:
                best = (r, k, mode)
    r, k, mode = best
    steps = (0, 3, 5, 7, 10) if mode == 'minor' else (0, 2, 4, 7, 9)
    base = 60 + k
    notes = [base + s for s in steps] + [base + 12 + s for s in steps]
    return k, mode, float(r), notes


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
    k, mode, r, notes = key_of(x, sr)
    print(f'KEY {NAMES[k]} {mode} (r={r:.2f}); pentatonic MIDI notes for tonal SFX: {notes}')
    print('Refine any boundary with 0.1 s levels: python -c "import vk_bgm" ... or slice db around it.')


if __name__ == '__main__':
    analyse(sys.argv[1])
