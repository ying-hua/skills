"""把剪映「我的预设」(复合片段预设) 注入到草稿 JSON 里。

预设存放在 E:\\JianYingProData\\Presets\\Combination\\Presets\\<名字>\\preset_draft\\draft_content.json，是明文。
结构：外层草稿 -> 一个视频片段(复合片段) -> materials.drafts 里的嵌套草稿(top)，top 里才是真正的文字/贴纸/音效等元素。
所有层级的嵌套草稿都平铺在外层的 materials.drafts 列表里。
"""
import copy
import json
import config
import os
import re
import subprocess
import uuid

PRESET_ROOT = config.get("JY_PRESET_ROOT")
CACHE_MUSIC = config.get("JY_CACHE_MUSIC")
_PH = re.compile(r"##_presetpath_placeholder_[^#]*_##")

# 剪映缓存里的音效(名字 -> 文件)，来自预设里的引用
SFX = {
    "砰": "90410dc9dc7946e63774ea33f428277e.mp3",       # 砰，拳击声
    "打字声": "b9d488609f6716f45f631bd6eb02a128.mp3",
    "回答正确": "d5e0a56a412c541c47726bd19c190e58.mp3",
    "提示音": "8c180184580af43efc914f665def9cdf.mp3",
    "嘟咚": "26fac03104a2059d7c1bb4ecd0eccb4d.mp3",     # 嘟咚，提示音1
    "任务完成": "93a6b50a8e0fec1cbf71e8283a3d0caa.mp3",
    "哇呜": "6007588a2192f94096511bba91692259.mp3",
    "写字": "915fe9c95242a717dd80f9d908d0f812.mp3",     # 写字，纸笔摩挲声
    "叮叮叮": "0a6d062a6406cc92499ec9babac2e185.mp3",
}
SFX_NAMES = {"砰": "砰，拳击声", "嘟咚": "嘟咚，提示音1", "写字": "写字，纸笔摩挲声"}
_LIB = None


def sound_library():
    """扫描所有组合预设，收集其中的音效：名字 -> (Preset, 片段, 素材)。"""
    global _LIB
    if _LIB is None:
        _LIB = {}
        root = os.path.join(PRESET_ROOT, "Presets")
        for n in os.listdir(root):
            if not os.path.exists(os.path.join(root, n, "preset_draft", "draft_content.json")):
                continue
            try:
                pre = Preset(n)
            except Exception:
                continue
            for t, seg, c, m, d in pre.elements():
                if c == "audios" and m.get("type") == "sound" and m.get("effect_id"):
                    _LIB.setdefault(m["name"], (pre, seg, m))
    return _LIB


_CACHE_IDX = None


def cache_index():
    """剪映素材面板的接口缓存(ressdk_db/*/rp.db 的 http_cache)：名字 -> (effect_id, 缓存 mp3 路径)。

    缓存文件名 = 接口记录里的 md5，所以凡是在剪映里试听/用过的音效都能定位到。
    """
    global _CACHE_IDX
    if _CACHE_IDX is None:
        import glob
        import sqlite3
        _CACHE_IDX = {}

        def walk(x):
            if isinstance(x, dict):
                ca = x.get("common_attr")
                if isinstance(ca, dict) and ca.get("md5") and ca.get("title") and ca.get("effect_id"):
                    p = os.path.join(CACHE_MUSIC, ca["md5"] + ".mp3")
                    if os.path.exists(p):
                        _CACHE_IDX.setdefault(ca["title"].strip(), (ca["effect_id"], p))
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)

        for db in glob.glob(os.path.join(os.path.dirname(CACHE_MUSIC), "ressdk_db", "*", "rp.db")):
            try:
                rows = sqlite3.connect(db).execute("select response_body from http_cache").fetchall()
            except Exception:
                continue
            for (body,) in rows:
                try:
                    walk(json.loads(body if isinstance(body, str) else body.decode("utf-8", "ignore")))
                except Exception:
                    pass
    return _CACHE_IDX


def lookup_sound(name, drafts_root=None):
    drafts_root = drafts_root or config.get("JY_DRAFTS_ROOT")
    """预设里没有的音效：先查剪映接口缓存索引(cache_index)；再退回从各草稿 key_value.json 查 id + 在缓存里找含该 id 的 mp3。"""
    import glob
    if name in cache_index():
        return cache_index()[name]
    sid = None
    for f in glob.glob(os.path.join(drafts_root, "*", "key_value.json")):
        try:
            d = json.load(open(f, encoding="utf-8")) or {}
        except Exception:
            continue
        for v in d.values():
            if isinstance(v, dict) and v.get("materialName") == name and v.get("materialCategory") == "audio":
                sid = v.get("materialId")
                break
        if sid:
            break
    if not sid:
        raise KeyError(f"找不到音效 {name} 的 id，请先在剪映里用一次")
    for f in os.listdir(CACHE_MUSIC):
        if f.endswith(".mp3"):
            with open(os.path.join(CACHE_MUSIC, f), "rb") as fh:
                if sid.encode() in fh.read():
                    return sid, os.path.join(CACHE_MUSIC, f)
    raise KeyError(f"音效 {name}({sid}) 未缓存，请先在剪映里试听一次")


def nid():
    return str(uuid.uuid4()).upper()


def us(t):
    return int(round(t * 1_000_000))


def _dur(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout
    return float(out.strip() or 0)


def _index(draft):
    idx = {}
    for k, v in draft["materials"].items():
        if isinstance(v, list):
            for m in v:
                if isinstance(m, dict) and "id" in m:
                    idx[m["id"]] = (k, m)
    return idx


def text_of(m):
    try:
        return json.loads(m.get("content", ""))["text"]
    except Exception:
        return re.sub(r"<[^>]+>", "", m.get("content", ""))


def set_text(m, new):
    """替换文字内容；长度变化时用第一段样式覆盖全文。"""
    c = json.loads(m["content"])
    old = c["text"]
    c["text"] = new
    if len(new) != len(old) or len(c.get("styles", [])) <= 1:
        st = c["styles"][0]
        st["range"] = [0, len(new)]
        c["styles"] = [st]
    m["content"] = json.dumps(c, ensure_ascii=False)
    if "words" in m and isinstance(m["words"], dict):
        m["words"] = {"end_time": [], "start_time": [], "text": []}


# 剪映文字宽度标定(用户 2026-10-17 第37期截图)：「弹上来（砰）」(UnboundedSans，字号 15，缩放 2.033)换成「Claude Code」
# 后左右都被画面切掉，可见的「laude Cod」≈ 画布 1080 宽 → 1 个 em(字号×缩放=1) ≈ 6.1 画布像素。
EM_PX = 6.1
FIT_W = 0.90   # 文字最宽占画布宽度


def text_width(m, scale):
    """估算文字素材在画布上的宽度(px)：用预设里的字体文件量；字体缺字形(中文)按 1em 算。"""
    from PIL import ImageFont
    c = json.loads(m["content"])
    st = c["styles"][0]
    em = EM_PX * float(st.get("size") or m.get("font_size") or 15) * scale
    fp = st.get("font", {}).get("path", "")
    w = 0.0
    try:
        f = ImageFont.truetype(fp, 100)
        for ch in c["text"]:
            w += (f.getlength(ch) / 100 if f.getmask(ch).getbbox() or ch == " " else 1.0) if ord(ch) < 0x2E80 else 1.0
    except OSError:
        w = sum(1.0 if ord(ch) >= 0x2E80 else 0.6 for ch in c["text"])
    return w * em


def fit_text(s, m, canvas_w=1080):
    """换完文字后如果太宽(会被画面切掉)，按比例缩小这个文字片段，并考虑它偏离中心的位置。"""
    clip = s.get("clip") or {}
    sc = clip.get("scale", {}).get("x", 1.0)
    dx = abs(clip.get("transform", {}).get("x", 0.0)) * canvas_w / 2
    room = min(canvas_w * FIT_W, 2 * (canvas_w / 2 - dx) - canvas_w * (1 - FIT_W))
    w = text_width(m, sc)
    if w > room:
        k = room / w
        clip["scale"] = {"x": sc * k, "y": clip["scale"].get("y", sc) * k}
        print(f"  文字「{json.loads(m['content'])['text']}」约 {w:.0f}px 超出画面，缩小到 {k:.0%}")


class Preset:
    def __init__(self, name):
        self.name = name
        p = os.path.join(PRESET_ROOT, "Presets", name, "preset_draft", "draft_content.json")
        raw = _PH.sub(PRESET_ROOT.replace("\\", "/"), open(p, encoding="utf-8").read())
        self.outer = json.loads(raw)
        self.G = {d["id"]: d for d in self.outer["materials"].get("drafts", [])}
        self.wrapper_seg = self.outer["tracks"][0]["segments"][0]
        top_id = next(r for r in self.wrapper_seg["extra_material_refs"] if r in self.G)
        self.top = self.G[top_id]["draft"]
        self.top_idx = _index(self.top)

    def elements(self):
        """[(track, seg, 素材类别, 素材, 描述)]"""
        out = []
        for t in self.top["tracks"]:
            for s in t["segments"]:
                cat, m = self.top_idx.get(s["material_id"], (None, {}))
                desc = m.get("material_name") or m.get("name") or (text_of(m) if cat == "texts" else "")
                out.append((t, s, cat, m, desc))
        return out

    def find(self, cat=None, desc=None, track_type=None):
        for t, s, c, m, d in self.elements():
            if (cat is None or c == cat) and (desc is None or d == desc) and (track_type is None or t["type"] == track_type):
                return t, s, c, m, d
        raise KeyError((self.name, cat, desc))


class Target:
    """生成好的草稿(明文 JSON)。"""

    def __init__(self, draft_dir):
        self.path = os.path.join(draft_dir, "draft_content.json")
        self.j = json.load(open(self.path, encoding="utf-8"))
        self.j["materials"].setdefault("drafts", [])
        self._draft_ids = {d["id"] for d in self.j["materials"]["drafts"]}
        self.lanes = {}  # 轨道组名 -> [(track, last_end_us)]

    def save(self):
        json.dump(self.j, open(self.path, "w", encoding="utf-8"), ensure_ascii=False)

    # ---------- 轨道

    def new_track(self, ttype, name, index=None):
        t = {"attribute": 0, "flag": 0, "id": nid(), "is_default_name": False, "name": name, "segments": [],
             "type": ttype}
        if index is None:
            self.j["tracks"].append(t)
        else:
            self.j["tracks"].insert(index, t)
        return t

    def lane(self, group, ttype, start, end, index=None):
        """在同组轨道里找一条不重叠的，没有就新建。"""
        lanes = self.lanes.setdefault(group, [])
        for i, (t, last) in enumerate(lanes):
            if start >= last:
                lanes[i] = (t, end)
                return t
        t = self.new_track(ttype, f"{group}{len(lanes) + 1}" if lanes else group, index)
        lanes.append((t, end))
        return t

    # ---------- 素材复制

    def _add_mat(self, cat, m):
        self.j["materials"].setdefault(cat, []).append(m)

    def _copy_draft_entry(self, G, did, new_id=True):
        """复制一个复合片段(嵌套草稿)条目及其内部引用的所有更深层复合片段。返回新 id。"""
        e = copy.deepcopy(G[did])
        # 递归带上内部引用的嵌套复合片段(保留原 id，去重)
        stack = [e["draft"]]
        while stack:
            d = stack.pop()
            for t in d.get("tracks", []):
                for s in t.get("segments", []):
                    for r in s.get("extra_material_refs", []):
                        if r in G and r not in self._draft_ids:
                            self._draft_ids.add(r)
                            sub = copy.deepcopy(G[r])
                            self._add_mat("drafts", sub)
                            stack.append(sub["draft"])
        if new_id:
            e["id"] = nid()
        if e["id"] not in self._draft_ids:
            self._draft_ids.add(e["id"])
            self._add_mat("drafts", e)
        return e

    def copy_segment(self, src_draft, G, seg, track, start, dur=None, edit_material=None, edit_combo=None,
                     volume=None, speed_src=None):
        """把预设里的一个片段(连同引用的素材)复制到 track，start/dur 单位秒。"""
        idx = _index(src_draft)
        s = copy.deepcopy(seg)
        s["id"] = nid()
        old_dur = seg["target_timerange"]["duration"]
        new_dur = us(dur) if dur is not None else old_dur
        s["target_timerange"] = {"start": us(start), "duration": new_dur}
        if s.get("source_timerange"):
            src_start = s["source_timerange"]["start"] if speed_src is None else 0
            s["source_timerange"] = {"start": src_start, "duration": new_dur}
        # 主素材
        cat, m = idx[seg["material_id"]]
        m2 = copy.deepcopy(m)
        m2["id"] = nid()
        if edit_material:
            edit_material(m2)
        self._add_mat(cat, m2)
        s["material_id"] = m2["id"]
        # 附加素材
        refs = []
        for r in seg.get("extra_material_refs", []):
            if r in G:
                e = self._copy_draft_entry(G, r)
                if edit_combo:
                    edit_combo(e)
                refs.append(e["id"])
            elif r in idx:
                c, mm = idx[r]
                mm2 = copy.deepcopy(mm)
                mm2["id"] = nid()
                if c == "material_animations":
                    # 用户 2026-10-13：所有素材只要入场动画，不要出场动画
                    mm2["animations"] = [a for a in mm2.get("animations", []) if a.get("type") != "out"]
                    for a in mm2["animations"]:
                        if a.get("type") in ("loop", "group"):
                            a["duration"] = new_dur - a.get("start", 0)
                self._add_mat(c, mm2)
                refs.append(mm2["id"])
        s["extra_material_refs"] = refs
        if volume is not None:
            s["volume"] = volume
        track["segments"].append(s)
        return s, m2

    # ---------- 高层操作

    def embed_combo(self, preset, start, end, group="背景", index=0, volume=0.0):
        """整段预设作为一个复合片段放进来(例如 1分钟背景)。"""
        t = self.lane(group, "video", us(start), us(end), index)
        s, _ = self.copy_segment(preset.outer, preset.G, preset.wrapper_seg, t, start, end - start, volume=volume)
        if s.get("source_timerange"):
            s["source_timerange"] = {"start": 0, "duration": us(end - start)}
        return s

    def element(self, preset, desc, start, dur=None, group=None, cat=None, text=None, edit_material=None,
                edit_combo=None, ttype=None):
        """把预设(top 层)里的某个元素复制出来，可改文字。"""
        t0, seg, c, m, d = preset.find(cat=cat, desc=desc, track_type=ttype)
        dur = dur if dur is not None else seg["target_timerange"]["duration"] / 1e6
        ttype = t0["type"]
        track = self.lane(group or f"预设{ttype}", ttype, us(start), us(start + dur))

        def em(mm):
            if text is not None:
                set_text(mm, text)
            if edit_material:
                edit_material(mm)

        return self.copy_segment(preset.top, preset.G, seg, track, start, dur, edit_material=em,
                                 edit_combo=edit_combo)

    def explode(self, preset, start, keep=None, text=None, group=None, until=None):
        """把一个小预设(文字/贴纸 + 音效)整体拆开放到 start 处。text 替换其中的文字。

        until：画面元素最晚到这里消失(比如片头「一天一个」出现前)，避免和下一段叠在一起；音效不截。
        """
        out = []
        for t0, seg, c, m, d in preset.elements():
            if keep and not keep(t0, c, d):
                continue
            st = start + seg["target_timerange"]["start"] / 1e6
            dur = seg["target_timerange"]["duration"] / 1e6
            if until is not None and t0["type"] != "audio":
                dur = min(dur, until - st)
                if dur < 0.1:
                    continue
            g = group or ("音效" if t0["type"] == "audio" else f"弹出{t0['type']}")
            track = self.lane(g, t0["type"], us(st), us(st + dur))

            def em(mm, c=c):
                if text is not None and c == "texts":
                    set_text(mm, text)

            s, m2 = self.copy_segment(preset.top, preset.G, seg, track, st, dur, edit_material=em)
            if text is not None and c == "texts":
                fit_text(s, m2)
            out.append((s, m2))
        return out

    def sound(self, template_preset, name, start, volume=1.0, max_dur=None, src_start=0.0):
        """放一个剪映音效。name 用剪映里的完整名字(如「砰，拳击声」「打字声」「哇呜」)，也接受 SFX_NAMES 里的简称。

        src_start：从素材第几秒开始(截掉开头静音)；max_dur：最多放多长(截掉拖太长的尾巴)。
        剪映靠 effect_id/resource_id 识别音效(不是 path)，所以必须复制带正确 id 的素材：
        优先从用户预设里找同名音效；找不到再查剪映接口缓存索引(cache_index)。
        """
        name = SFX_NAMES.get(name, name)
        lib = sound_library()
        if name in lib:
            pre, seg, m = lib[name]
            d = m["duration"] / 1e6 - src_start
            if max_dur:
                d = min(d, max_dur)
            track = self.lane("音效", "audio", us(start), us(start + d))
            s, _ = self.copy_segment(pre.top, pre.G, seg, track, start, d, volume=volume)
        else:
            sid, path = lookup_sound(name)
            d = _dur(path) - src_start
            if max_dur:
                d = min(d, max_dur)
            _, seg, c, m, _ = next(e for e in template_preset.elements()
                                   if e[2] == "audios" and e[3].get("type") == "sound")
            track = self.lane("音效", "audio", us(start), us(start + d))

            def em(mm):
                mm.update(path=path.replace("\\", "/"), name=name, duration=us(_dur(path)), effect_id=sid,
                          resource_id=sid, request_id="", category_id="", category_name="")

            s, _ = self.copy_segment(template_preset.top, template_preset.G, seg, track, start, d, edit_material=em,
                                     volume=volume)
        s["source_timerange"] = {"start": us(src_start), "duration": us(d)}
        return s

    def music(self, path, name, start, end, volume=0.2, template_preset=None):
        """BGM：本地文件，淡出交给剪映。"""
        _, seg, c, m, _ = next(e for e in template_preset.elements() if e[2] == "audios" and e[3].get("type") == "sound")
        track = self.lane("BGM", "audio", us(start), us(end))

        try:
            mid, _ = lookup_sound(name)  # 剪映曲库音乐同样靠 id 识别
        except KeyError:
            mid = ""

        def em(mm):
            mm.update(path=path.replace("\\", "/"), name=name, type="music", duration=us(_dur(path)),
                      effect_id=mid, resource_id=mid, music_id=mid, request_id="", category_id="", category_name="")

        s, _ = self.copy_segment(template_preset.top, template_preset.G, seg, track, start, end - start,
                                 edit_material=em, volume=volume)
        s["source_timerange"] = {"start": 0, "duration": us(end - start)}
        return s
