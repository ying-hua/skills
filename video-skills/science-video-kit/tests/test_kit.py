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
        self.assertGreater(img[150:250, 600:1320].max(), 200, 'template title must be visible on frame 0')

    def test_text_markup_and_tags(self):
        import vk_core as v
        v.set_tags({'k': (1.0, 0.2, 0.2)})
        self.assertEqual([c for c, _ in v.parse('[k]AB[/]C', v.CREAM)], ['A', 'B', 'C'])
        self.assertEqual(v.parse('[k]A[/]', v.CREAM)[0][1], (1.0, 0.2, 0.2))
        cv = v.Canvas()
        v.add_text(cv, '中文 ABC 123', 960, 540, size=60)
        self.assertGreater(v.finish(cv, 0)[500:580, 700:1220].max(), 200)

    def test_font_override_and_tracer(self):
        import vk_core as v
        f = v._resolve(v.FONT_LAT2)
        self.assertNotEqual(v.text_width('Var', 60, font=f), 0)
        cv = v.Canvas()
        v.add_text(cv, 'VAR!', 960, 540, size=60, anim=None, font=f)
        self.assertGreater(v.finish(cv, 0)[500:580, 860:1060].max(), 200)
        # tracer must draw on every call (it was once wrapped in an lru_cache by accident)
        self.assertFalse(hasattr(v.tracer, 'cache_info'))


    def test_text_boxes_and_zones(self):
        import vk_core as v
        cv = v.Canvas()
        v.add_text(cv, '封面标题', v.W * 0.7, v.H * 0.5, size=80, anim=None, glow=0.5)
        v.finish(cv, 0)
        self.assertEqual(len(cv.text_boxes), 1)
        x0, y0, x1, y1 = cv.text_boxes[0][1]
        self.assertTrue(x0 > v.W * 0.5 and y0 > v.H * 0.4 and y1 < v.H * 0.6)
        corners = [(0, 0, 0.5, 0.25), (0, 0.87, 0.5, 1)]
        self.assertEqual(v.text_in_zones(cv, corners), [])
        cv2_ = v.Canvas()
        v.add_text(cv2_, '左上角', 200, 100, size=60, anim=None)
        v.finish(cv2_, 0)
        self.assertEqual(len(v.text_in_zones(cv2_, corners)), 1)

    def test_persist_surface_survives_keep_clear(self):
        import vk_core as v
        s = v.to_surface(np.full((8, 8, 3), 0.5, np.float32), persist=True)
        v._KEEP.clear()
        cv = v.Canvas()
        v.paint_img(cv.c, s, v.W // 2, v.H // 2)
        self.assertAlmostEqual(v.finish(cv, 0)[v.H // 2 + 4, v.W // 2 + 4].mean() / 255, 0.5, delta=0.12)


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

    def test_chiptune_and_choir(self):
        import vk_audio as A
        x = A.square(440.0, 0.3)
        spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
        fr = np.fft.rfftfreq(len(x), 1 / A.SR)
        self.assertLess(spec[fr > 8000].max(), spec.max() * 1e-3, 'square must be band-limited')
        self.assertTrue(np.all(np.isfinite(A.tri(110.0, 0.3))))
        c = A.choir([60, 64, 67], 1.0)
        self.assertTrue(np.all(np.isfinite(c)) and np.abs(c).max() > 0.01)

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
            import vk_audio as A
            from scipy.io import wavfile
            tone = (0.25 * np.sin(2 * np.pi * 440 * np.arange(2 * A.SR) / A.SR) * 32767).astype(np.int16)
            wavfile.write(os.path.join(d, 'tone.wav'), A.SR, tone)
            lv = run('vk_scan.py', 'levels', 'tone.wav').stdout
            self.assertIn('0:-15', lv)          # 0.25 amplitude sine -> -15 dBFS RMS
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
