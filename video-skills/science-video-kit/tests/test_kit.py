"""Smoke tests for science-video-kit:  python tests/test_kit.py
Needs numpy, scipy, pycairo, opencv-python, Pillow, ffmpeg/ffprobe. The GPU test is skipped without moderngl/OpenGL 4.3."""
import contextlib, io, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

import numpy as np

SKILL = Path(__file__).resolve().parents[1]
SCRIPTS, TEMPLATES = SKILL / 'scripts', SKILL / 'assets' / 'templates'
sys.path[:0] = [str(SCRIPTS), str(TEMPLATES)]


def has_ffmpeg():
    return shutil.which('ffmpeg') and shutil.which('ffprobe')


class CoreTests(unittest.TestCase):
    def test_template_frame0_has_title(self):
        import scenes
        img = scenes.render_frame(0.0, 0)
        self.assertEqual(img.shape, (1080, 1920, 3))
        self.assertGreater(img[150:250, 600:1320].max(), 200, 'hook title must be visible on frame 0')

    def test_text_markup_and_tags(self):
        import vk_core as v
        v.set_tags({'k': (1.0, 0.2, 0.2)})
        self.assertEqual([c for c, _ in v.parse('[k]AB[/]C', v.CREAM)], ['A', 'B', 'C'])
        self.assertEqual(v.parse('[k]A[/]', v.CREAM)[0][1], (1.0, 0.2, 0.2))
        cv = v.Canvas()
        v.add_text(cv, '中文 ABC 123', 960, 540, size=60)
        self.assertGreater(v.finish(cv, 0)[500:580, 700:1220].max(), 200)


class AudioTests(unittest.TestCase):
    def test_all_generators_finite(self):
        import inspect
        import vk_audio as A
        args = {'f': 440.0, 'd': 0.5, 'notes': [60, 64, 67], 'x': np.random.randn(4800), 'm': 60, 'f0': 300.0, 'f1': 3000.0}
        skip = {'render_cues', 'click_rain', 'load_bgm', 'duck', 'master', 'P', 'norm', 'filt'}
        for name, fn in inspect.getmembers(A, inspect.isfunction):
            if fn.__module__ != 'vk_audio' or name.startswith('_') or name in skip:
                continue
            req = [p.name for p in inspect.signature(fn).parameters.values() if p.default is inspect.Parameter.empty]
            if not all(r in args for r in req):
                continue
            out = fn(*[args[r] for r in req])
            self.assertTrue(np.all(np.isfinite(out)), name)

    def test_bus_and_master(self):
        import vk_audio as A
        bus = A.Bus(2.0)
        A.render_cues(bus, [(0.0, 'gunshot', 1.0, -0.5), (1.0, 'pop', 0.7, 0.5)])
        A.click_rain(bus, [(0.2 + i * 0.01, 0.5, 0.0) for i in range(50)])
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'm.wav')
            with contextlib.redirect_stdout(io.StringIO()):
                A.master(A.duck(np.zeros_like(bus.x), bus.x) + bus.x, 2.0, p)
            self.assertGreater(os.path.getsize(p), 100000)


@unittest.skipUnless(has_ffmpeg(), 'ffmpeg/ffprobe not on PATH')
class PipelineTests(unittest.TestCase):
    def test_bgm_hits(self):
        import vk_audio as A
        from scipy.io import wavfile
        import vk_bgm
        x = np.concatenate([A.noise(4.0) * 0.01, A.noise(4.0) * 0.4])
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'b.wav')
            wavfile.write(p, A.SR, (x * 32767).astype(np.int16))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                vk_bgm.analyse(p)
        line = [l for l in buf.getvalue().splitlines() if l.startswith('HITS')][0]
        self.assertIn('4.0', line)

    def test_render_scan_finalize(self):
        with tempfile.TemporaryDirectory() as d:
            for f in list(SCRIPTS.glob('*.py')) + list(TEMPLATES.glob('*.py')):
                shutil.copy(f, d)
            Path(d, 'tiny.py').write_text('from scenes import *\nTOTAL = 0.5\n', encoding='utf-8')
            env = dict(os.environ, PYTHONIOENCODING='utf-8')
            run = lambda *c: subprocess.run([sys.executable, *c], cwd=d, env=env, check=True, capture_output=True, text=True)
            run('vk_render.py', 'render', '--module', 'tiny', '--workers', '1')
            out = run('vk_scan.py', 'spikes', 'out/chunks/c000.mp4').stdout
            self.assertIn('SUSPECT FRAMES: 0', out)
            Path(d, 'out', 'soundtrack.wav').write_bytes(b'')
            import vk_audio as A
            with contextlib.redirect_stdout(io.StringIO()):
                A.master(A.Bus(0.5).x + 1e-3 * np.random.randn(int(1.5 * A.SR), 2), 0.5, os.path.join(d, 'out', 'soundtrack.wav'))
            run('vk_finalize.py', '--out', 'out/t.mp4', '--mb', '0.5')
            self.assertTrue(Path(d, 'out', 't.mp4').exists())


class GLTests(unittest.TestCase):
    def test_gl_render_and_nan_guard(self):
        try:
            import vk_gl
            R = vk_gl.GL(320, 180)
        except Exception as e:
            self.skipTest(f'no GL: {e}')
        R.load('nan', 'out vec4 o; void main(){ float z = 0.; o = vec4(gl_FragCoord.x < 160. ? 0./z : 1., 0.5, 0.2, 1.); }')
        img = R.render('nan', lambda t: {}, 0.0, spp=2)
        self.assertEqual(img.shape, (180, 320, 3))
        self.assertTrue(np.isfinite(img.astype(float)).all())
        self.assertGreater(img[:, 200:].mean(), img[:, :100].mean())


if __name__ == '__main__':
    unittest.main(verbosity=2)
