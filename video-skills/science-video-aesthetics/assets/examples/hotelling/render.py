"""python render.py --stills 0,5,20 --sheet out/s.png   |   python render.py --chunk i n  (render frames slice)"""
import argparse, os, subprocess, sys, time
import numpy as np
from PIL import Image
from gfx import W, H, FPS
import story

ap = argparse.ArgumentParser()
ap.add_argument('--stills', default='')
ap.add_argument('--sheet', default='out/sheet.png')
ap.add_argument('--cols', type=int, default=3)
ap.add_argument('--chunk', nargs=2, type=int)
args = ap.parse_args()

if args.stills:
    ims = []
    for t in [float(x) for x in args.stills.split(',')]:
        t0 = time.time(); ims.append(story.frame(t)); print(f't={t} {time.time()-t0:.2f}s', flush=True)
    c = args.cols
    while len(ims) % c: ims.append(np.zeros_like(ims[0]))
    sheet = np.concatenate([np.concatenate(ims[i:i + c], 1) for i in range(0, len(ims), c)], 0)
    Image.fromarray(sheet).resize((sheet.shape[1] // 2, sheet.shape[0] // 2), Image.LANCZOS).save(args.sheet)
    sys.exit()

i, n = args.chunk
N = int(story.DUR * FPS)
f0, f1 = N * i // n, N * (i + 1) // n
os.makedirs('out/chunks', exist_ok=True)
out = f'out/chunks/c{i:02d}.mp4'
cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS),
       '-i', '-', '-c:v', 'libx264', '-preset', 'medium', '-crf', '14', '-pix_fmt', 'yuv420p', out]
p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
st = time.time()
for f in range(f0, f1):
    p.stdin.write(story.frame((f + 0.5) / FPS).tobytes())
    if (f - f0) % 150 == 0:
        print(f'chunk {i}: {f-f0}/{f1-f0} {time.time()-st:.0f}s', flush=True)
p.stdin.close(); p.wait()
print('done', i, time.time() - st)
