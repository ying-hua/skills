"""本机路径配置。每个人的剪映安装位置不同，**不要在代码里写死路径**。

优先级：环境变量 > 工作区根目录的 `config.json` > 自动探测默认值。
`config.json` 示例(键名同下表，由 Agent 向用户询问后写入，不要提交到仓库)：
{
  "JY_DRAFTS_ROOT": "...剪映草稿目录...",
  "JY_PRESET_ROOT": "...JianYingProData/Presets/Combination...",
  "JY_CACHE_MUSIC": "...JianYingProData/Cache/music...",
  "STICKER_DIR": "...贴纸 PNG 目录(可选)...",
  "FONT_DIR": "...字体目录(可选)..."
}
"""
import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
_FILE = {}
_p = os.path.join(_ROOT, "config.json")
if os.path.exists(_p):
    with open(_p, encoding="utf-8") as _f:
        _FILE = json.load(_f)

_LOCAL = os.environ.get("LOCALAPPDATA", "")
_DEFAULTS = {
    "JY_DRAFTS_ROOT": os.path.join(_LOCAL, "JianYingPro", "User Data", "Projects", "com.lveditor.draft"),
    "JY_PRESET_ROOT": os.path.join(_LOCAL, "JianYingPro", "User Data", "Presets", "Combination"),
    "JY_CACHE_MUSIC": os.path.join(_LOCAL, "JianYingPro", "User Data", "Cache", "music"),
    "STICKER_DIR": os.path.join(_ROOT, "stickers"),
    "FONT_DIR": r"C:\Windows\Fonts",
}


def get(key):
    return os.environ.get(key) or _FILE.get(key) or _DEFAULTS[key]


def require_dir(key, what):
    """路径不存在就报错并告诉 Agent 去问用户，而不是悄悄用错位置。"""
    p = get(key)
    if not os.path.isdir(p):
        sys.exit(f"[config] {what} 不存在: {p}\n请向用户确认真实位置，写入 config.json 的 {key}，或设环境变量 {key}。")
    return p
