"""Parallel, resumable chunk renderer + contact sheets. Your scenes module must expose
    TOTAL (seconds)  and  render_frame(t, frame_idx) -> uint8 HxWx3

  python vk_render.py sheet  --module scenes --times 0,0.8,2,5 [--out out/sheet.png] [--cols 2] [--tile 960]
  python vk_render.py render --module scenes [--workers 5] [--fps 30] [--chunk 150] [--from 40 --to 58]
  python vk_render.py concat [--module scenes] [--out out/video_noaudio.mp4]

Chunks go to out/chunks/cNNN.mp4 (written as .tmp then renamed -> safe to kill and resume; delete a chunk to redo it).
--from/--to (seconds) re-renders only the chunks overlapping that span (they are deleted first), then concats.
Memory: every worker holds its own caches (~0.6-1 GB at 1080p with big textures). 16 GB RAM -> <= 5 workers.
GPU (moderngl) projects: use --workers 1 (one context; parallel GPU contexts just contend).
"""
import argparse, importlib, os, subprocess, sys, time

sys.path.insert(0, os.getcwd())
os.environ.setdefault('OMP_NUM_THREADS', '1')   # avoid BLAS oversubscription inside workers


def _job(a):
    mod, i, f0, f1, fps = a
    S = importlib.import_module(mod)
    out = f'out/chunks/c{i:03d}.mp4'
    if os.path.exists(out):
        return out, 0.0
    st = time.time()
    p = None
    for f in range(f0, f1):
        fr = S.render_frame((f + 0.5) / fps, f)
        if p is None:
            h, w = fr.shape[:2]
            p = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                                  '-s', f'{w}x{h}', '-r', str(fps), '-i', '-', '-c:v', 'libx264', '-preset', 'medium',
                                  '-crf', '16', '-pix_fmt', 'yuv420p', out + '.tmp.mp4'], stdin=subprocess.PIPE)
        p.stdin.write(fr.tobytes())
    p.stdin.close()
    p.wait()
    os.replace(out + '.tmp.mp4', out)
    return out, time.time() - st


def jobs_for(S, mod, fps, chunk):
    n = int(round(S.TOTAL * fps))
    return [(mod, i, f0, min(n, f0 + chunk), fps) for i, f0 in enumerate(range(0, n, chunk))]


def concat(S, mod, fps, chunk, out):
    js = jobs_for(S, mod, fps, chunk)
    missing = [j[1] for j in js if not os.path.exists(f'out/chunks/c{j[1]:03d}.mp4')]
    if missing:
        sys.exit(f'missing chunks: {missing}')
    with open('out/chunks/list.txt', 'w') as f:
        for j in js:
            f.write(f"file 'c{j[1]:03d}.mp4'\n")
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', 'out/chunks/list.txt',
                    '-c', 'copy', out], check=True)
    print('->', out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['sheet', 'render', 'concat'])
    ap.add_argument('--module', default='scenes')
    ap.add_argument('--times', default='')
    ap.add_argument('--out', default='')
    ap.add_argument('--cols', type=int, default=2)
    ap.add_argument('--tile', type=int, default=960)
    ap.add_argument('--workers', type=int, default=5)
    ap.add_argument('--fps', type=int, default=30)
    ap.add_argument('--chunk', type=int, default=150)
    ap.add_argument('--from', dest='t_from', type=float, default=None)
    ap.add_argument('--to', dest='t_to', type=float, default=None)
    a = ap.parse_args()
    os.makedirs('out/chunks', exist_ok=True)
    S = importlib.import_module(a.module)
    if a.cmd == 'sheet':
        import numpy as np
        from PIL import Image
        ims = []
        for t in [float(x) for x in a.times.split(',')]:
            st = time.time()
            im = Image.fromarray(S.render_frame(t, int(t * a.fps)))
            ims.append(np.asarray(im.resize((a.tile, int(a.tile * im.height / im.width)), Image.LANCZOS)))
            print(f't={t:.2f} {time.time() - st:.2f}s', flush=True)
        while len(ims) % a.cols:
            ims.append(np.zeros_like(ims[0]))
        out = a.out or 'out/sheet.png'
        Image.fromarray(np.concatenate([np.concatenate(ims[i:i + a.cols], 1) for i in range(0, len(ims), a.cols)], 0)).save(out)
        print('->', out)
        return
    if a.cmd == 'render':
        from multiprocessing import Pool
        js = jobs_for(S, a.module, a.fps, a.chunk)
        if a.t_from is not None:
            lo, hi = a.t_from * a.fps, (a.t_to if a.t_to is not None else S.TOTAL) * a.fps
            js = [j for j in js if j[3] > lo and j[2] < hi]
            for j in js:
                p = f'out/chunks/c{j[1]:03d}.mp4'
                if os.path.exists(p):
                    os.remove(p)
        st = time.time()
        if a.workers <= 1:
            for k, j in enumerate(js):
                r, dt = _job(j)
                print(f'{k + 1}/{len(js)} {r} {dt:.0f}s  total {time.time() - st:.0f}s', flush=True)
        else:
            with Pool(a.workers) as pool:
                for k, (r, dt) in enumerate(pool.imap_unordered(_job, js)):
                    print(f'{k + 1}/{len(js)} {r} {dt:.0f}s  total {time.time() - st:.0f}s', flush=True)
    concat(S, a.module, a.fps, a.chunk, a.out or 'out/video_noaudio.mp4')


if __name__ == '__main__':
    main()
