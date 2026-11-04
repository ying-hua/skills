"""第N期 模板(来自第31期 Ponytail)。复制为 epNN/build.py 后修改 EP/NAME/路径/各镜头坐标与时间。"""
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))

import fx
import jy
import onsets
import opening
import preset as P
import preview
from pyJianYingDraft import FontType, TextBorder, TrackType

EP = 31
NAME = "Ponytail"
DRAFT = f"AI工具-{EP}-Ponytail-v3"
MAT = r"D:\Desktop\temp\视频流\AI工具\31-ponytail"
VOICE = os.path.join(MAT, "audio", "audio.mp3")
LANDS = glob.glob(os.path.join(MAT, "*_landscape.mp4"))
LAND = LANDS[0] if LANDS else None  # 3D 运镜还在做，没有时用仓库页占位
REC = os.path.join(MAT, "屏幕录制 2026-10-06 145809.mp4")
BGM = (r"E:\JianYingProData\Cache\music\ae69c6c143e4bfc72ac8165ac509b03c.mp3", "Mane")
PREVIEW_BG = os.path.join(HERE, "..", "assets", "bg_AI小成_60s.mp4")
A = os.path.join(HERE, "assets")
os.makedirs(A, exist_ok=True)
GREEN = (36, 186, 96)
RED = (235, 60, 60)


def frame(t):
    return jy.extract_frame(REC, t, os.path.join(A, f"rec_{t}.png"))


def a(name):
    return os.path.join(A, name)


LAYERS = [("画面", TrackType.video), ("压暗", TrackType.video), ("浮起卡片", TrackType.video),
          ("流光", TrackType.video), ("框", TrackType.video), ("贴纸", TrackType.video), ("字幕", TrackType.text)]
tl = jy.Timeline(DRAFT, LAYERS)
SFX = []
POPS = []

f_top = frame(10.0)      # GitHub 仓库页
f_readme = frame(20.0)   # 中文 README：代码减少约 54%（最多 94%）
f_head = frame(14.0)     # README 头图(马尾辫头像)
f_diff = frame(34.0)     # 官网：-48 +1 代码对比
f_rules = frame(41.0)    # 官网：7 条规则
f_bench = frame(48.0)    # 官网：基准数据
f_inst = frame(52.3)     # 官网：安装命令

# ---------------------------------------------------------------- 0. 钩子：这个skill能直接减少你90%的Token消耗
HOOK_END = 3.67
if LAND:
    # landscape 只有 3.43s，放慢到 0.93 撑满钩子；高亮句从右移到左，1.0 倍保证整句在画面内
    tl.image("画面", LAND, 0.0, HOOK_END, 1.0, 556, 800, src_start=0.0, speed=0.93)
else:
    tl.zshot(f_head, 0.0, HOOK_END, (840, 140, 1460, 700))
POPS += [("弹上来（砰）", 1.57, "减少90%", HOOK_END), ("直接出现（叮）", 2.83, "Token消耗", HOOK_END)]

# 片头(预设)：一天一个 / 超实用的 / 网站 / 第31期 / 今天分享的是 —— 吸附到配音真实音节起点
OPEN = dict(onsets.opening_times(os.path.join(HERE, "transcript.json"), VOICE), t_end=7.53)

# ---------------------------------------------------------------- 1. 记住这个项目名字 → 144K Star
s = tl.zshot(f_top, 7.53, 9.07, (40, 70, 540, 270))
tl.pop(s, (186, 154, 322, 190), 7.69, 9.07, f_top, a("pop_name"))
s = tl.zshot(f_top, 9.07, 12.13, (1250, 70, 1750, 270))
tl.pop(s, (1528, 153, 1675, 188), 9.30, 12.13, f_top, a("pop_star"))
SFX += [("任务完成", 7.69, 0.8), ("任务完成", 9.30, 0.8)]

# ---------------------------------------------------------------- 2. 在保证安全可用的基础上
s = tl.zshot(f_bench, 12.13, 14.07, (900, 220, 1400, 380))
tl.outline(s, (1175, 255, 1335, 352), 12.78, 14.07, a("box_safe.png"))
SFX.append(("提示音", 12.78, 0.6))

# ---------------------------------------------------------------- 3. 代码量最高降低94%
s = tl.zshot(f_readme, 14.07, 16.80, (800, 500, 1300, 580))
tl.outline(s, (930, 525, 1065, 552), 15.42, 16.80, a("box_94.png"), pad=8)
SFX.append(("提示音", 15.42, 0.6))
POPS.append(("文字砸下来（砰）", 16.32, "-94%", 16.80))

# ---------------------------------------------------------------- 4. 速度也能跟着提升
s = tl.zshot(f_bench, 16.80, 18.33, (880, 220, 1380, 380))
tl.outline(s, (1000, 255, 1120, 352), 17.90, 18.33, a("box_fast.png"))
SFX.append(("提示音", 17.90, 0.6))

# ---------------------------------------------------------------- 5. 它不是靠粗暴删代码
tl.zshot(f_diff, 18.33, 19.93, (467, 320, 1430, 600))
tag1 = fx.sticker_tag("不是乱删!", a("st_不乱删.png"), bg=RED, emoji="黄脸_05.png")
tl.sticker(tag1["png"], 18.87, 19.93, 720, 600, 470, rotation=-4)
SFX.append(("砰", 18.87, 0.8))

# ---------------------------------------------------------------- 6. 而是用了7条规则
s = tl.zshot(f_rules, 19.93, 21.40, (440, 230, 960, 700))
tl.outline(s, (460, 252, 500, 685), 20.67, 21.40, a("box_7.png"), pad=8)
wow7 = fx.sticker_wow(["7条", "规则"], a("st_7条规则.png"), emoji="黄脸_02.png", emoji_scale=0.6, emoji_pos="corner")
tl.sticker(wow7["png"], 20.60, 21.40, 600, 300, 430, rotation=6)
SFX.append(("任务完成", 20.60, 0.8))

# ---------------------------------------------------------------- 7. 找到一条实现目标的最短路径
s = tl.zshot(f_rules, 21.40, 23.80, (440, 120, 1000, 330))
tl.outline(s, (465, 165, 950, 208), 22.88, 23.80, a("box_path.png"))
SFX.append(("提示音", 22.88, 0.6))

# ---------------------------------------------------------------- 8~10. 三条规则：逐条框出
for (st, en, focus, box, t, nm) in [
    (23.80, 25.13, (440, 215, 940, 330), (465, 256, 702, 290), 23.95, "r01"),
    (25.13, 26.47, (440, 350, 940, 465), (465, 389, 840, 424), 25.32, "r03"),
    (26.47, 28.13, (440, 545, 940, 660), (465, 586, 725, 621), 26.67, "r06"),
]:
    s = tl.zshot(f_rules, st, en, focus)
    tl.outline(s, box, t, en, a(f"box_{nm}.png"))
    SFX.append(("提示音", t, 0.6))

# ---------------------------------------------------------------- 11. 使用也很方便
tl.zshot(f_inst, 28.13, 29.20, (440, 40, 1440, 420))
POPS.append(("直接出现（嘟噜）", 28.67, "超方便", 29.20))

# ---------------------------------------------------------------- 12. 直接把安装命令丢给你的agent
s = tl.zshot(f_inst, 29.20, 31.40, (460, 70, 900, 180))
tl.outline(s, (488, 92, 862, 158), 29.69, 31.40, a("box_cmd.png"))
SFX.append(("提示音", 29.69, 0.6))

# ---------------------------------------------------------------- 13. 它就会自动完成部署
tl.zshot(f_inst, 31.40, 32.93, (440, 200, 1440, 420))
tag2 = fx.sticker_tag("自动部署", a("st_自动部署.png"), bg=GREEN, emoji="黄脸_03.png")
tl.sticker(tag2["png"], 31.90, 32.93, 760, 620, 430, rotation=-4)
SFX.append(("砰", 31.90, 0.8))

# ---------------------------------------------------------------- 14. 项目完全开源
s = tl.zshot(f_top, 32.93, 34.13, (1340, 560, 1798, 860))
tl.outline(s, (1368, 640, 1488, 662), 33.52, 34.13, a("box_mit.png"))
SFX.append(("提示音", 33.52, 0.6))

# ---------------------------------------------------------------- 15. 结尾：太贴心了吧
END = 35.50
tl.zshot(f_head, 34.13, END, (840, 140, 1460, 700))
wow = fx.sticker_wow(["太贴心", "了吧"], a("st_太贴心.png"), emoji="黄脸_07.png", emoji_scale=0.6, emoji_pos="corner")
tl.sticker(wow["png"], 34.20, END, 540, 900, 600, rotation=-4)
SFX.append(("哇呜", 34.20, 0.8))

# ---------------------------------------------------------------- 字幕
REPL = [("Git Hub", "GitHub"), ("GitHub", "GitHub"), ("star", "Star"), ("TOKEN", "Token"), ("超时用", "超实用")]
HL = ["skill", "90%", "Token", "项目名字", "GitHub", "144K", "Star", "安全可用", "94%", "速度", "提升", "粗暴删代码",
      "7条规则", "最短路径", "存在吗", "标准库", "不多写", "很方便", "安装命令", "agent", "自动完成部署", "完全开源", "太贴心"]
subs = jy.phrases(os.path.join(HERE, "transcript.json"), replace=REPL)
for i, (st, en, text) in enumerate(subs):
    if OPEN["t_yi"] - 0.05 <= st < OPEN["t_card"] or st >= 34.1:  # 片头大字、结尾大贴纸期间不放字幕
        continue
    nxt = subs[i + 1][0] if i + 1 < len(subs) else END
    en = min(max(en + 0.15, st + 0.6), nxt, END)
    tl.text("字幕", text, st, en, 11, y=-0.6, font=FontType.抖音美好体, border=TextBorder(color=(0, 0, 0), width=45),
            highlights=[h for h in HL if h in text])


def build():
    path = tl.save(VOICE, bg_path=None, draft_name=DRAFT)
    T = P.Target(path)
    T.embed_combo(P.Preset("1分钟背景"), 0, END)
    card = opening.make_card_image(f_head, (600, 140, 1700, 784), a("open_card_1368.png"))
    op = opening.add_opening(T, EP, NAME, card, **OPEN)
    for name, t, text, until in POPS:
        T.explode(P.Preset(name), t, text=text, until=until)
    for name, t, vol in SFX:
        T.sound(op, name, t, volume=vol)
    T.music(BGM[0], BGM[1], 0, END, volume=0.18, template_preset=op)
    T.save()
    return path


if __name__ == "__main__":
    path = build()
    print("草稿:", path, "时长", END, "| landscape:", LAND or "占位(未找到 *_landscape.mp4)")
    times = [0.3, 1.8, 3.5, 8.0, 10.0, 13.0, 15.6, 18.0, 19.0, 20.8, 23.0, 24.2, 25.5, 27.0, 28.7, 30.0, 32.2, 33.7, 34.6]
    preview.sheet(tl, times, os.path.join(HERE, "preview.png"), bg_path=PREVIEW_BG, cols=9, scale=0.25)
