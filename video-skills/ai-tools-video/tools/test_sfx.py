"""音效测试草稿：每 2 秒一个音效，画面上写着音效名。"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import pyJianYingDraft as draft
from pyJianYingDraft import TextSegment, TextStyle, TrackSpec, TrackType, trange, SEC
import config
import preset as P

NAME = sys.argv[1] if len(sys.argv) > 1 else "claude-音效测试"
names = sys.argv[2].split("|") if len(sys.argv) > 2 else list(P.sound_library()) + ["叮", "啵1", "鼠标点击声", "唰"]
# 这个脚本是「新建」一个音效测试草稿，不是检查已有草稿！2026-10-16 误传第36期草稿名，把成品草稿覆盖成了音效测试
if not NAME.startswith("claude-音效测试") and os.path.exists(os.path.join(config.get("JY_DRAFTS_ROOT"), NAME)):
    sys.exit(f"拒绝：草稿「{NAME}」已存在。本脚本会新建并覆盖草稿，只能用 claude-音效测试* 的名字")
sc = draft.DraftFolder(config.get("JY_DRAFTS_ROOT")).create_draft(NAME, 1080, 1920, 30, allow_replace=True)
sc.append_track(TrackSpec(TrackType.text, "音效名"))
for i, n in enumerate(names):
    sc.add_segment(TextSegment(n, trange(i * 2 * SEC, 2 * SEC), style=TextStyle(size=14, align=1)), "音效名")
sc.save()
T = P.Target(os.path.join(config.get("JY_DRAFTS_ROOT"), NAME))
op = P.Preset("片头2")
for i, n in enumerate(names):
    try:
        T.sound(op, n, i * 2 + 0.2)
        print("ok", n)
    except KeyError as e:
        print("skip", e)
T.save()
