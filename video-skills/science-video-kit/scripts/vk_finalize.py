"""Mux + master + upload encode (writes ONLY the upload file).
  python vk_finalize.py --out out/<name>.mp4 [--video out/video_noaudio.mp4] [--audio out/soundtrack.wav] [--mb 130] [--lufs -14]
Two-pass x264 sized to ~--mb MB total; ffmpeg loudnorm to --lufs (short-video platforms normalise to about -14).
"""
import argparse, os, subprocess

ap = argparse.ArgumentParser()
ap.add_argument('--video', default='out/video_noaudio.mp4')
ap.add_argument('--audio', default='out/soundtrack.wav')
ap.add_argument('--out', required=True)
ap.add_argument('--mb', type=float, default=130)
ap.add_argument('--lufs', type=float, default=-14)
ap.add_argument('--abr', type=int, default=256)
a = ap.parse_args()
os.makedirs('cache', exist_ok=True)


def run(c):
    subprocess.run(c, check=True)


dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', a.video],
                           capture_output=True, text=True).stdout)
vk = int(a.mb * 8 * 1000 / dur - a.abr - 40)
print(f'duration {dur:.1f}s -> video {vk} kbps')
run(['ffmpeg', '-y', '-loglevel', 'error', '-i', a.audio, '-af', f'loudnorm=I={a.lufs}:TP=-1.0:LRA=11', '-ar', '48000',
     'cache/_audio_ln.wav'])
common = ['-c:v', 'libx264', '-preset', 'slow', '-b:v', f'{vk}k', '-pix_fmt', 'yuv420p']
run(['ffmpeg', '-y', '-loglevel', 'error', '-i', a.video, *common, '-pass', '1', '-passlogfile', 'cache/x264', '-an',
     '-f', 'mp4', 'NUL' if os.name == 'nt' else '/dev/null'])
run(['ffmpeg', '-y', '-loglevel', 'error', '-i', a.video, '-i', 'cache/_audio_ln.wav', *common, '-pass', '2',
     '-passlogfile', 'cache/x264', '-c:a', 'aac', '-b:a', f'{a.abr}k', '-map', '0:v', '-map', '1:a', '-shortest',
     '-movflags', '+faststart', a.out])
print('->', a.out, f'{os.path.getsize(a.out) / 1e6:.1f} MB')
