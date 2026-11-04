"""每期换着用的 BGM 和音效(用户 2026-10-16：BGM 别老是 Mane，提示音太同质化)。

BGM：工作区 BGM候选/ 里的 4 首按期数轮换(本地文件、空 id，剪映能正常播放——Mane 一直就是这样放的)。
音效：同一类用途准备几个，Cycle 依次取，名字都在剪映缓存 preset.cache_index() 里(用户已试听确认)。
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BGM_DIR = os.path.join(HERE, "..", "BGM候选")
BGMS = ["Mane", "Manten Diloty", "Montagen bandido", "The invincible king 2"]


def bgm(ep):
    """第 ep 期用哪首：按期数轮换。返回 (路径, 名字)。"""
    name = BGMS[ep % len(BGMS)]
    return os.path.abspath(os.path.join(BGM_DIR, name + ".mp3")), name


# 用户 2026-10-16 拉黑：太难听，永远不用
BLACKLIST = {"叮，收银机提示音1", "闪亮登场音效", "哐，撞击轻响", "滴，提示音", "哇哦不错哟，女声",
             "轻快的嗖"}  # 用户 2026-10-16 第36期：素材里连响 3 声，别用

# 只用用户在剪映里「收藏」的音效(用户 2026-10-16 给的收藏截图，共 23 个)，按用途分组。
# 剪映不在本地存收藏列表，所以这里手抄；用户收藏变了就更新 FAVORITES 和分组。
FAVORITES = ["科幻按钮音", "科技点击系统音", "科幻点击叮的音效素材", "游戏点击 音效", "激活出现提示", "科技电波音",
             "叮咚（紧张）", "轻快的嗖", "唰", "写字，纸笔摩挲声", "啵1", "哇呜", "Ding，可爱提示音", "嘟咚，提示音1",
             "鼠标点击声", "打字声", "提示音", "亮一下", "任务完成", "回答正确", "砰，拳击声", "碰撞", "啵，轻气泡音3"]
# 框选/聚焦框的提示音
CUE = ["提示音", "科幻按钮音", "Ding，可爱提示音", "科技点击系统音", "嘟咚，提示音1", "游戏点击 音效", "啵1",
       "科幻点击叮的音效素材", "鼠标点击声", "啵，轻气泡音3"]
# 标签贴纸(sticker_tag)砸下来
HIT = ["砰，拳击声", "碰撞", "唰", "叮咚（紧张）"]
# 渐变大字贴纸(sticker_wow)
WOW = ["哇呜", "科技电波音", "激活出现提示", "砰，拳击声"]
# 项目名 / Star 流光框
POP = ["任务完成", "亮一下", "回答正确"]
# 打字/写字画面(有需要时用)
WRITE = ["打字声", "写字，纸笔摩挲声"]

for _g in (CUE, HIT, WOW, POP, WRITE):
    assert not BLACKLIST & set(_g), BLACKLIST & set(_g)
    assert set(_g) <= set(FAVORITES), set(_g) - set(FAVORITES)


def available(name):
    """草稿里能不能放这个音效：用户预设里有(preset.sound_library)，或剪映缓存里有(cache_index)。
    没有的(用户没试听过、也不在预设里)放进去会变成别的声音，Cycle 会跳过。"""
    import preset
    return name in preset.sound_library() or name in preset.cache_index()

# 开头的静音(秒)：放音效时要提前这么多，声音才和画面同时出来(用户 2026-10-16：「叮」前 20 帧、「提示音」前 9 帧是空的)。
# 用户手量的优先；其他从剪映缓存文件自动量(-35dB 以上算有声)。
LEAD_FIXED = {"叮": 20 / 30, "提示音": 9 / 30}
_lead_cache = {}


def lead(name):
    if name in LEAD_FIXED:
        return LEAD_FIXED[name]
    if name not in _lead_cache:
        import subprocess
        import numpy as np
        import preset
        hit = preset.cache_index().get(name)
        if not hit and name in preset.sound_library():   # 只在预设里的：从预设素材路径量
            m = preset.sound_library()[name][2]
            hit = (None, m.get("path", ""))
            if not os.path.exists(hit[1]):
                hit = None
        if not hit:                      # 预设里的音效(如「砰」)不在缓存，之前用着都正常
            _lead_cache[name] = 0.0
        else:
            raw = subprocess.run(["ffmpeg", "-v", "error", "-i", hit[1], "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                                 capture_output=True).stdout
            x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
            w = 160
            db = 20 * np.log10(np.array([np.sqrt(np.mean(x[i:i + w] ** 2)) for i in range(0, len(x) - w, w)]) + 1e-6)
            k = int(np.argmax(db > -35))
            _lead_cache[name] = k * w / 16000 if k * w / 16000 > 0.1 else 0.0   # 不到 3 帧的忽略
    return _lead_cache[name]


def sfx_time(name, t):
    """想让声音在 t 秒响起，音效片段该放在哪(提前掉开头静音，不早于 0)。"""
    return max(0.0, t - lead(name))


class Cycle:
    """c = Cycle(CUE, start=ep)；c() 依次返回下一个名字。start 按期数错开，每期开头的音效也不一样。"""

    def __init__(self, names, start=0):
        ok = [n for n in names if n not in BLACKLIST and available(n)]
        skip = [n for n in names if n not in ok and n not in BLACKLIST]
        if skip:
            print("音效暂时取不到(请用户在剪映里试听或放进预设)，先跳过:", "、".join(skip))
        self.names, self.i = ok, start

    def __call__(self):
        n = self.names[self.i % len(self.names)]
        self.i += 1
        return n
