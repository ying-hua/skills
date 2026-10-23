"""Token-free QA on rendered video (prints numbers, never images):
  python vk_scan.py spikes out/chunks/c0*.mp4     single-frame flicker / black-block (NaN bloom) detector
  python vk_scan.py levels out/final.mp4          mean luma per second (accidental black-outs / white-outs)
  python vk_scan.py sheet out/final.mp4 0,1,17,64 [out/final_sheet.png]   small contact sheet of the deliverable
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
    elif c == 'sheet':
        sheet(sys.argv[2], [float(x) for x in sys.argv[3].split(',')],
              sys.argv[4] if len(sys.argv) > 4 else 'out/final_sheet.png')
