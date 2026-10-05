"""TEMPLATE audio.py - SFX from scene cues (+ either a supplied BGM or your own synthesized score).
  python audio.py            -> out/soundtrack.wav   (vk_finalize does loudnorm later)
"""
import os
from vk_audio import *
import scenes as S

BGM = None                  # path to a supplied bgm (mp3/wav), or None to compose a score below


def score(bus):
    """Synthesized score, used when no BGM is supplied. Placeholder: replace with your own."""
    bpm = 90
    beat = 60 / bpm
    for k in range(int(S.TOTAL / beat)):
        bus.add(kick(0.8), k * beat, 0.5)


def build():
    sfx = Bus(S.TOTAL)
    render_cues(sfx, S.all_cues())
    if BGM and os.path.exists(BGM):
        music = load_bgm(BGM, S.TOTAL)
    else:
        mb = Bus(S.TOTAL)
        score(mb)
        music = mb.x
    mix = duck(music, sfx.x) * 0.62 + sfx.x * 0.55
    os.makedirs('out', exist_ok=True)
    master(mix, S.TOTAL, 'out/soundtrack.wav')


if __name__ == '__main__':
    build()
