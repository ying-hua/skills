"""Token-free QA on rendered video (prints numbers, never images):
  python vk_scan.py spikes out/chunks/c0*.mp4     single-frame flicker / black-block (NaN bloom) detector
  python vk_scan.py levels out/final.mp4          mean luma per second (accidental black-outs / white-outs)
  python vk_scan.py sheet out/final.mp4 0,1,17,64 [out/final_sheet.png]   small contact sheet of the deliverable
  python vk_scan.py whine out/sfx.wav [--fmin 2500 --secs 3]     sustained high narrowband tones (shrill whistles)
Large 'maxdiff' alone is normal at hard cuts and flashes; investigate 'spikes' and 'blocks'.
"""
import subprocess, sys
import numpy as np


def frames(f, w=96, h=54):
    p = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', f, '-vf', f'scale={w}:{h}', '-f', 'rawvideo',
                        '-pix_fmt', 'gray', '-'], capture_output=True)
    return np.frombuffer(p.stdout, np.uint8).reshape(-1, h, w).astype(np.float32)


def spikes(files):
    bad = 0
    for f in files:
        a = frames(f, 192, 108)
        d = np.abs(np.diff(a, axis=0)).mean((1, 2))
        sp, blk = [], []
        for i in range(1, len(a) - 1):
            prev, cur, nxt = a[i - 1], a[i], a[i + 1]
            if np.abs(cur - prev).mean() > 12 and np.abs(nxt - prev).mean() < 4:
                sp.append(i)
            if (np.abs(cur - prev) > 80).mean() > 0.002 and (np.abs(nxt - prev) > 80).mean() < 0.0005:
                blk.append(i)
        bad += len(sp) + len(blk)
        print(f'{f}: {len(a)} fr  maxdiff {d.max():.1f}@{int(d.argmax())}  spikes {sp}  blocks {blk}')
    print('SUSPECT FRAMES:', bad)


AUDIO_EXT = ('.wav', '.mp3', '.flac', '.m4a', '.aac', '.ogg')


def audio_levels(f):
    """per-second RMS / peak in dBFS of an audio file (stereo summed to mono)"""
    p = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', f, '-ac', '1', '-ar', '8000', '-f', 'f32le', '-'],
                       capture_output=True)
    x = np.frombuffer(p.stdout, np.float32)
    n = len(x) // 8000
    x = x[:n * 8000].reshape(n, 8000)
    rms = 20 * np.log10(np.sqrt((x.astype(np.float64) ** 2).mean(1)) + 1e-9)
    pk = 20 * np.log10(np.abs(x).max(1) + 1e-9)
    print('per-second RMS dBFS (peak):')
    print(' '.join(f'{i}:{r:.0f}({q:.0f})' for i, (r, q) in enumerate(zip(rms, pk))))
    quiet = [i for i in range(n) if rms[i] < rms.max() - 30]
    print(f'loudest {rms.max():.1f} dB @ {int(rms.argmax())}s; seconds >30 dB below loudest: {quiet}')


def levels(f):
    """video: per-second mean brightness; audio files: per-second RMS/peak dBFS"""
    if f.lower().endswith(AUDIO_EXT):
        return audio_levels(f)
    a = frames(f, 32, 18)
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v', '-show_entries', 'stream=r_frame_rate',
                        '-of', 'csv=p=0', f], capture_output=True, text=True).stdout.strip().split('/')
    fps = float(r[0]) / float(r[1])
    m = a.mean((1, 2))
    print(' '.join(f'{i}:{m[int(i * fps):int((i + 1) * fps)].mean():.0f}' for i in range(int(len(m) / fps))))


def whine(f, fmin=2500.0, secs=3, share=0.05):
    """flag runs of >= secs seconds where one narrow band above fmin carries >= share of the second's energy and
    stays within ~1/3 semitone - the sustained shrill tone (pad fed Hz, high sine bed, feedback whistle) that
    per-second RMS cannot see. Check the SFX/score bus alone; a supplied song can trip it by design."""
    from scipy.signal import stft
    p = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', f, '-ac', '1', '-ar', '32000', '-f', 'f32le', '-'],
                       capture_output=True)
    x = np.frombuffer(p.stdout, np.float32).astype(np.float64)
    fr, tm, Z = stft(x, 32000, nperseg=4096, noverlap=2048)
    pw = np.abs(Z) ** 2
    hi = fr >= fmin
    runs, cur, prev = [], [], None
    for s in range(int(len(x) / 32000)):
        ps = pw[:, (tm >= s) & (tm < s + 1)].mean(1)
        tot = ps.sum() + 1e-15
        i = int(np.argmax(np.where(hi, ps, 0)))
        ok = ps[i] / tot >= share and tot > 1e-9
        if ok and prev is not None and abs(np.log2(fr[i] / prev)) < 1 / 36:
            cur.append((s, fr[i]))
        else:
            if len(cur) >= secs:
                runs.append(cur)
            cur = [(s, fr[i])] if ok else []
        prev = fr[i] if ok else None
    if len(cur) >= secs:
        runs.append(cur)
    for r in runs:
        print(f'WHINE {r[0][0]}-{r[-1][0] + 1}s  ~{np.mean([q for _, q in r]):.0f} Hz')
    print('SUSTAINED HIGH TONES:', len(runs))
    return runs


def sheet(f, ts, out):
    from PIL import Image
    ims = []
    for t in ts:
        p = subprocess.run(['ffmpeg', '-loglevel', 'error', '-ss', str(t), '-i', f, '-frames:v', '1', '-vf', 'scale=640:-2',
                            '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True)
        ims.append(np.frombuffer(p.stdout, np.uint8).reshape(-1, 640, 3))
    while len(ims) % 2:
        ims.append(np.zeros_like(ims[0]))
    Image.fromarray(np.concatenate([np.concatenate(ims[i:i + 2], 1) for i in range(0, len(ims), 2)], 0)).save(out)
    print('->', out)


if __name__ == '__main__':
    c = sys.argv[1]
    if c == 'spikes':
        spikes(sys.argv[2:])
    elif c == 'levels':
        levels(sys.argv[2])
    elif c == 'whine':
        a = sys.argv[2:]
        kw = {k[2:]: float(v) for k, v in zip(a[1::2], a[2::2])}
        whine(a[0], kw.get('fmin', 2500.0), int(kw.get('secs', 3)))
    elif c == 'sheet':
        sheet(sys.argv[2], [float(x) for x in sys.argv[3].split(',')],
              sys.argv[4] if len(sys.argv) > 4 else 'out/final_sheet.png')
