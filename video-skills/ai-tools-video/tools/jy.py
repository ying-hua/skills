"""剪映草稿构建工具：在 pyJianYingDraft 之上封装「镜头 / 叠加层 / 字幕」等高层操作。

坐标约定：画布 1080x1920，像素坐标原点在左上角；时间单位为秒(内部转微秒)。
"""
import json
import os
import subprocess
from copy import deepcopy

from PIL import Image

import pyJianYingDraft as draft
from pyJianYingDraft import (AudioSegment, ClipSettings, IntroType, KeyframeProperty, MaskType, MixModeType,
                             OutroType, TextBorder, TextIntro, TextOutro, TextSegment, TextStyle, Timerange,
                             TrackSpec, TrackType, TransitionType, VideoMaterial, VideoSegment)

import config
import fx

CW, CH = 1080, 1920
SEC = 1_000_000
STICKER_SCALE = 1.45  # 用户反馈：贴纸(生气了/复刻TA)要更大
DRAFTS_ROOT = config.get("JY_DRAFTS_ROOT")


def us(t):
    return int(round(t * SEC))


def tr(start, end):
    return Timerange(us(start), us(end) - us(start))


_size_cache = {}


def media_size(path):
    if path in _size_cache:
        return _size_cache[path]
    if path.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        with Image.open(path) as im:
            wh = im.size
    else:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                              "stream=width,height", "-of", "csv=p=0", path], capture_output=True, text=True).stdout
        w, h = out.strip().split(",")[:2]
        wh = (int(w), int(h))
    _size_cache[path] = wh
    return wh


def fit(w, h):
    """剪映把素材「适应」到画布时的缩放系数。"""
    return min(CW / w, CH / h)


def clip_at(path, k, cx, cy, alpha=1.0, rotation=0.0):
    """让素材以 k (画布像素/素材像素) 的比例显示，中心位于画布 (cx, cy)。"""
    w, h = media_size(path)
    s = k / fit(w, h)
    return ClipSettings(scale_x=s, scale_y=s, transform_x=(cx - CW / 2) / (CW / 2),
                        transform_y=(CH / 2 - cy) / (CH / 2), alpha=alpha, rotation=rotation)


def ease_out(p):
    return 1 - (1 - p) ** 3


def ease_in_out(p):
    return 3 * p * p - 2 * p * p * p


# ---------------------------------------------------------------- 关键词高亮字幕

class HLText(TextSegment):
    """支持局部关键词变色的文本片段(导出为多段 style)。"""

    def __init__(self, text, timerange, highlights=(), hl_color=(1.0, 0.84, 0.0), **kw):
        super().__init__(text, timerange, **kw)
        self.highlights = [h for h in highlights if h and h in text]
        self.hl_color = hl_color

    def export_material(self):
        ret = super().export_material()
        if not self.highlights:
            return ret
        cj = json.loads(ret["content"])
        base = cj["styles"][0]
        n = len(self.text)
        flags = [False] * n
        for h in self.highlights:
            i = self.text.find(h)
            while i >= 0:
                for j in range(i, i + len(h)):
                    flags[j] = True
                i = self.text.find(h, i + len(h))
        styles, a = [], 0
        while a < n:
            b = a
            while b < n and flags[b] == flags[a]:
                b += 1
            s = deepcopy(base)
            s["range"] = [a, b]
            if flags[a]:
                s["fill"]["content"]["solid"]["color"] = list(self.hl_color)
            styles.append(s)
            a = b
        cj["styles"] = styles
        ret["content"] = json.dumps(cj, ensure_ascii=False)
        return ret


# ---------------------------------------------------------------- 时间线

class Shot:
    """一个页面镜头：静帧 + 缓动关键帧(缩放/平移)。keys: [(t相对秒, (x0,y0,x1,y1), 目标宽度px, 中心y)]"""

    def __init__(self, path, start, end, keys, off=(0, 0)):
        # off: 原始截图坐标 -> 当前素材坐标 的偏移(裁剪成卡片后)
        self.path, self.start, self.end = path, start, end
        self.off = off
        self.keys = [(t, (b[0] - off[0], b[1] - off[1], b[2] - off[0], b[3] - off[1]), tw, cy)
                     for t, b, tw, cy in keys]
        self.w, self.h = media_size(path)

    def _key_tf(self, key):
        _, (x0, y0, x1, y1), tw, cy = key
        k = tw / (x1 - x0)
        fcx, fcy = (x0 + x1) / 2, (y0 + y1) / 2
        return k, CW / 2 + (self.w / 2 - fcx) * k, cy + (self.h / 2 - fcy) * k

    def tf(self, t):
        """镜头内相对时间 t 时的变换 (k, 素材中心cx, cy)。"""
        ks = self.keys
        if t <= ks[0][0]:
            return self._key_tf(ks[0])
        for a, b in zip(ks, ks[1:]):
            if a[0] <= t <= b[0]:
                p = ease_in_out((t - a[0]) / max(1e-6, b[0] - a[0]))
                ta, tb = self._key_tf(a), self._key_tf(b)
                return tuple(x + (y - x) * p for x, y in zip(ta, tb))
        return self._key_tf(ks[-1])

    def map(self, t, sx, sy):
        """原始截图坐标 (sx, sy) 在镜头相对时间 t 时对应的画布坐标。"""
        k, cx, cy = self.tf(t)
        sx, sy = sx - self.off[0], sy - self.off[1]
        return cx + (sx - self.w / 2) * k, cy + (sy - self.h / 2) * k, k


def guard_draft(name):
    """同名草稿已被剪映打开/保存过(有 .backup 目录，或 draft_content.json 已加密读不成 JSON)就拒绝覆盖。

    2026-10-13 第33期 v2 被重建覆盖过一次——用户可能正在里面改。要重建就换新名字(-v3、-v4)。
    """
    d = os.path.join(DRAFTS_ROOT, name)
    if not os.path.isdir(d):
        return
    touched = os.path.isdir(os.path.join(d, ".backup"))
    try:
        json.load(open(os.path.join(d, "draft_content.json"), encoding="utf-8"))
    except Exception:
        touched = True
    if touched:
        raise SystemExit(f"草稿「{name}」已被剪映打开/保存过，不覆盖。请换一个新名字。")


def fill_focus(path, focus, tw=1080, cy=900):
    """调整焦点框，使放大到 tw 宽后素材盖满 CW×CH 画布：k 至少 max(CW/w, CH/h)，可见窗口不越出素材边界。"""
    w, h = media_size(path)
    x0, y0, x1, y1 = focus
    k = max(tw / (x1 - x0), CW / w, CH / h)
    fw = tw / k
    fcx, fcy = (x0 + x1) / 2, (y0 + y1) / 2
    # 画布左右边 / 上下边 对应的素材坐标
    half_w = CW / 2 / k
    fcx = min(max(fcx, half_w), w - half_w)
    top, bot = cy / k, (CH - cy) / k
    fcy = min(max(fcy, top), h - bot)
    fh = (y1 - y0)
    return (fcx - fw / 2, fcy - fh / 2, fcx + fw / 2, fcy + fh / 2)


class Timeline:
    """收集所有片段，最后按图层顺序分配轨道并写入草稿。"""

    def __init__(self, name, layers):
        # layers: [(图层名, TrackType)] 自下而上
        self.name = name
        self.layers = layers
        self.items = {l: [] for l, _ in layers}
        self.total = 0.0
        self.meta = {}  # id(seg) -> 预览用信息

    def add(self, layer, seg, start, end, meta=None):
        self.items[layer].append((start, end, seg))
        self.total = max(self.total, end)
        if meta is not None:
            meta.update(layer=layer, start=start, end=end)
            self.meta[id(seg)] = meta
        return seg

    # ---------- 视觉片段

    def image(self, layer, path, start, end, k, cx, cy, alpha=1.0, rotation=0.0, intro=None, intro_dur=None,
              outro=None, outro_dur=None, src_start=None, speed=None, volume=0.0):
        """放置图片/视频素材。k=显示比例(画布像素/素材像素)。"""
        kw = {}
        if src_start is not None:
            dur = end - start
            sp = speed or 1.0
            kw["source_timerange"] = Timerange(us(src_start), us(dur * sp))
            kw["speed"] = sp
        seg = VideoSegment(path, tr(start, end), clip_settings=clip_at(path, k, cx, cy, alpha, rotation),
                           volume=volume, **kw)
        if intro:
            seg.add_animation(intro, us(intro_dur) if intro_dur else None)
        if outro:
            seg.add_animation(outro, us(outro_dur) if outro_dur else None)
        return self.add(layer, seg, start, end, dict(type="img", path=path, k=k, cx=cx, cy=cy, alpha=alpha,
                                                     rot=rotation, kf=[], src_start=src_start, speed=speed or 1.0,
                                                     intro=(intro_dur or 0.3) if intro else None,
                                                     outro=(outro_dur or 0.3) if outro else None))

    def keyframes(self, seg, path, frames, start=0.0):
        """frames: [(相对秒, k, cx, cy, alpha或None)]，自动写入缩放/位置/透明度关键帧。"""
        w, h = media_size(path)
        f0 = fit(w, h)
        if id(seg) in self.meta:
            self.meta[id(seg)]["kf"].extend(frames)
        for t, k, cx, cy, a in frames:
            off = us(t)
            if k is not None:
                seg.add_keyframe(KeyframeProperty.uniform_scale, off, k / f0)
            if cx is not None:
                seg.add_keyframe(KeyframeProperty.position_x, off, (cx - CW / 2) / (CW / 2))
                seg.add_keyframe(KeyframeProperty.position_y, off, (CH / 2 - cy) / (CH / 2))
            if a is not None:
                seg.add_keyframe(KeyframeProperty.alpha, off, a)

    def shot(self, path, start, end, keys, layer="画面", window=None, radius=6, transition=None,
             trans_dur=None, steps=4):
        """页面镜头。window=(宽, 高) 画布像素：按首个关键帧把截图裁成圆角卡片(带投影)。"""
        if window:
            probe = Shot(path, start, end, keys)
            ww, wh = window
            xs, ys = [], []
            for key in keys:  # 所有关键帧下窗口覆盖区域的并集
                k_, cx_, cy_ = probe.tf(key[0])
                sx0 = (CW / 2 - ww / 2 - cx_) / k_ + probe.w / 2
                sy0 = (key[3] - wh / 2 - cy_) / k_ + probe.h / 2
                xs += [sx0, sx0 + ww / k_]
                ys += [sy0, sy0 + wh / k_]
            k0 = probe.tf(0)[0]
            box = (max(0, int(min(xs))), max(0, int(min(ys))), min(probe.w, int(max(xs))), min(probe.h, int(max(ys))))
            src = Image.open(path).convert("RGB").crop(box)
            card = src.convert("RGBA")
            card.putalpha(fx.rounded_mask(card.width, card.height, int(radius / k0) + 1))
            img, (mx, my) = fx.add_shadow(card, blur=max(6, int(18 / k0)), offset=(0, int(10 / k0)),
                                          opacity=0.55)
            base, _ = os.path.splitext(path)
            path = f"{base}_win_{box[0]}_{box[1]}_{box[2]}_{box[3]}.png"
            img.save(path)
            _size_cache.pop(path, None)
            sh = Shot(path, start, end, keys, off=(box[0] - mx, box[1] - my))
        else:
            sh = Shot(path, start, end, keys)
        k0, cx0, cy0 = sh.tf(0)
        seg = VideoSegment(path, tr(start, end), clip_settings=clip_at(path, k0, cx0, cy0))
        self.meta[id(seg)] = dict(type="img", path=path, k=k0, cx=cx0, cy=cy0, alpha=1.0, rot=0.0, kf=[],
                                  src_start=None, speed=1.0, layer=layer, start=start, end=end)
        # 缓动：每段之间插几个中间关键帧
        frames = []
        for a, b in zip(keys, keys[1:]):
            for i in range(steps + 1):
                t = a[0] + (b[0] - a[0]) * i / steps
                k, cx, cy = sh.tf(t)
                frames.append((t, k, cx, cy, None))
        if len(keys) > 1:
            self.keyframes(seg, path, frames)
        if transition:
            seg.add_transition(transition, duration=us(trans_dur) if trans_dur else None)
        self.add(layer, seg, start, end)
        return sh

    def zshot(self, path, start, end, focus, tw=1080, cy=900, zoom_from=0.78, at=0.0, dur=0.2, layer="画面",
              transition=None, trans_dur=None, src_start=None, speed=1.0, fill=False):
        """大画面镜头：焦点区域 focus 铺满 tw 宽，只打两个关键帧——在 at 秒处 dur 秒内从 zoom_from 倍快速放大。

        path 也可以是视频：src_start=从素材第几秒开始，speed=播放速度(<1 放慢)，画面边放边推。
        放大要大胆(用户 2026-10-13)：焦点框尽量取小，3336 宽的素材焦点约 600px(剪映 560%)；重点落在画面
        中间偏上(焦点中心对准 cy)。**不要求铺满画布，露出背景没关系**——宁可露背景也要大、要居中。
        fill=True 才强制铺满(会把素材边缘的重点推到画面边上，用户不要，默认关)。
        """
        if fill:
            focus = fill_focus(path, focus, tw, cy)
        keys = [(at, focus, tw * zoom_from, cy), (at + dur, focus, tw, cy)]
        sh = Shot(path, start, end, keys)
        k0, cx0, cy0 = sh.tf(0)
        kw = {}
        if src_start is not None:
            kw = dict(source_timerange=Timerange(us(src_start), us((end - start) * speed)), speed=speed, volume=0.0)
        seg = VideoSegment(path, tr(start, end), clip_settings=clip_at(path, k0, cx0, cy0), **kw)
        self.meta[id(seg)] = dict(type="img", path=path, k=k0, cx=cx0, cy=cy0, alpha=1.0, rot=0.0, kf=[],
                                  src_start=src_start, speed=speed, layer=layer, start=start, end=end)
        frames = [(t, *sh.tf(t), None) for t in (at, at + dur)]
        self.keyframes(seg, path, frames)
        if transition:
            seg.add_transition(transition, duration=us(trans_dur) if trans_dur else None)
        self.add(layer, seg, start, end)
        return sh

    # ---------- 叠加效果

    def outline(self, shot, box, start, end, out_png, color=(255, 90, 30), pad=10, stroke=7, layer="框",
                dashed=False, radius=12):
        x0, y0, x1, y1 = box
        t = start - shot.start
        X0, Y0, k = shot.map(t, x0, y0)
        X1, Y1, _ = shot.map(t, x1, y1)
        info = fx.make_outline(out_png, int(X1 - X0 + pad * 2), int(Y1 - Y0 + pad * 2), color=color,
                               stroke=stroke, radius=radius, dashed=dashed)
        self.image(layer, out_png, start, end, 1.0, (X0 + X1) / 2, (Y0 + Y1) / 2,
                   intro=IntroType.放大, intro_dur=0.25)

    def spot(self, shot, box, start, end, src_png, out_png, grow=1.15, dim=0.5, color=(240, 30, 60), max_w=1000,
             layer="浮起卡片", pad=22):
        """聚焦框(用户 2026-10-14 参考小W，取代简单的 outline)：背景压暗，框住的元素原地做成白底卡片、
        稍微放大(grow)并回弹，外圈红色粗虚线圆角框。卡片不飞走，停在元素原位置。"""
        t = max(start - shot.start, max(f[0] for f in shot.keys))  # 镜头放大结束后的位置
        x0, y0, x1, y1 = box
        X, Y, k = shot.map(t, (x0 + x1) / 2, (y0 + y1) / 2)
        grow = min(grow, max_w / ((x1 - x0 + 2 * pad) * k))
        info = fx.make_spot(src_png, box, k * grow, out_png, color=color, pad=pad)
        black = fx.make_solid(os.path.join(os.path.dirname(out_png), "black.png"))
        seg = self.image("压暗", black, start, end, 1.0, CW / 2, CH / 2, alpha=0.0)
        self.keyframes(seg, black, [(0, None, None, None, 0.0), (0.2, None, None, None, dim)])
        k0 = 1.0 / grow
        seg = self.image(layer, out_png, start, end, 1.0, X, Y)
        self.keyframes(seg, out_png, [(0.00, k0, None, None, 0.0), (0.06, None, None, None, 1.0),
                                      (0.16, 1.06, None, None, None), (0.24, 0.98, None, None, None),
                                      (0.30, 1.0, None, None, None)])

    def pop(self, shot, box, start, end, src_png, asset_prefix, pop=1.25, lift=0.0, dim=0.62,
            neon_color=(255, 40, 170), center=(CW / 2, 820), max_w=980):
        """example 第8秒效果：背景压暗，目标区域做成白卡片浮起放大，外圈粉色流光环绕。

        center(用户 2026-10-13，第33期发布后反馈)：重点要在画面中间偏上，不能贴边。素材里的元素常在边缘
        (录屏顶部的项目名/Star，fill 放大后被推到画面最上面)，所以卡片从原位置浮起时同时飞到 center；
        center=None 则原地浮起(只上移 lift)。max_w：卡片放大后最宽多少画布像素。
        """
        t = start - shot.start
        x0, y0, x1, y1 = box
        X0, Y0, k = shot.map(t, (x0 + x1) / 2, (y0 + y1) / 2)
        X, Y = center if center else (X0, Y0 - lift)
        card = fx.make_card(src_png, box, asset_prefix + "_card.png", pad=14, radius=14)
        pop = min(pop, max_w / (card["card_w"] * k))
        neon_dur = end - start - 0.3
        neon = fx.make_neon(card["card_w"], card["card_h"], card["radius"], asset_prefix + "_neon.mp4",
                            duration=neon_dur + 0.2, color=neon_color)
        # 1) 压暗层
        black = fx.make_solid(os.path.join(os.path.dirname(asset_prefix), "black.png"))
        seg = self.image("压暗", black, start, end, 1.0, CW / 2, CH / 2, alpha=0.0)
        self.keyframes(seg, black, [(0, None, None, None, 0.0), (0.25, None, None, None, dim)])
        # 2) 浮起卡片(带回弹)
        kc = k * pop
        seg = self.image("浮起卡片", card["png"], start, end, k, X, Y)
        self.keyframes(seg, card["png"], [
            (0.00, k, X0, Y0, 0.0), (0.08, None, None, None, 1.0),
            (0.20, kc * 1.06, X, Y, None), (0.30, kc * 0.98, X, Y, None), (0.38, kc, X, Y, None)])
        # 3) 流光(滤色混合)
        seg = VideoSegment(neon["mp4"], tr(start + 0.3, end),
                           clip_settings=clip_at(neon["mp4"], kc, X, Y), volume=0.0)
        seg.set_mix_mode(MixModeType.滤色)
        self.add("流光", seg, start + 0.3, end, dict(type="img", path=neon["mp4"], k=kc, cx=X, cy=Y, alpha=1.0,
                                                   rot=0.0, kf=[], src_start=0.0, speed=1.0, blend="screen"))

    def sticker(self, png, start, end, cx, cy, width, layer="贴纸", intro=IntroType.放大, intro_dur=0.3,
                outro=None, outro_dur=0.2, rotation=0.0, wobble=False):
        w, h = media_size(png)
        width = min(CW * 0.95, width * STICKER_SCALE)
        k = width / w
        seg = self.image(layer, png, start, end, k, cx, cy, rotation=rotation, intro=intro, intro_dur=intro_dur,
                         outro=outro, outro_dur=outro_dur)
        if wobble:
            frames = []
            t, d = 0.35, end - start - 0.25
            i = 0
            while t < d:
                frames.append((t, k * (1.0 if i % 2 == 0 else 1.05), None, None, None))
                t += 0.45
                i += 1
            if len(frames) > 1:
                self.keyframes(seg, png, frames)
        return seg

    # ---------- 文本

    def text(self, layer, text, start, end, size, color=(1, 1, 1), y=0.0, x=0.0, bold=True, font=None,
             border=None, highlights=(), hl_color=(1.0, 0.84, 0.0), intro=None, intro_dur=None, outro=None,
             outro_dur=None, shadow=False):
        seg = HLText(text, tr(start, end), highlights=highlights, hl_color=hl_color, font=font,
                     style=TextStyle(size=size, bold=bold, color=color, align=1),
                     border=border, clip_settings=ClipSettings(transform_x=x, transform_y=y),
                     shadow=draft.TextShadow(alpha=0.6, color=(0, 0, 0), diffuse=12, distance=4, angle=-45)
                     if shadow else None)
        if intro:
            seg.add_animation(intro, us(intro_dur) if intro_dur else None)
        if outro:
            seg.add_animation(outro, us(outro_dur) if outro_dur else None)
        return self.add(layer, seg, start, end, dict(type="text", text=text, size=size, color=color, x=x, y=y,
                                                     highlights=highlights, hl_color=hl_color,
                                                     border=border is not None))

    # ---------- 写入草稿

    def save(self, voice_path, bg_path=None, draft_name=None):
        guard_draft(draft_name or self.name)
        folder = draft.DraftFolder(DRAFTS_ROOT)
        script = folder.create_draft(draft_name or self.name, CW, CH, fps=30, allow_replace=True)
        if bg_path:
            self.add("背景", VideoSegment(bg_path, tr(0, self.total), volume=0.0), 0, self.total)
        for layer, ttype in self.layers:
            items = sorted(self.items[layer], key=lambda x: x[0])
            if not items:
                continue
            lanes = []  # 每条子轨道最后结束时间(微秒)
            assign = []
            for s, e, seg in items:
                for i, last in enumerate(lanes):
                    if us(s) >= last:
                        lanes[i] = us(e)
                        assign.append(i)
                        break
                else:
                    lanes.append(us(e))
                    assign.append(len(lanes) - 1)
            names = [layer if len(lanes) == 1 else f"{layer}{i + 1}" for i in range(len(lanes))]
            for n in names:
                script.append_track(TrackSpec(ttype, n))
            for (s, e, seg), i in zip(items, assign):
                script.add_segment(seg, names[i])
        script.append_track(TrackSpec(TrackType.audio, "配音"))
        script.add_segment(AudioSegment(voice_path, tr(0, min(self.total, audio_dur(voice_path)))), "配音")
        script.save()
        return os.path.join(DRAFTS_ROOT, draft_name or self.name)


def audio_dur(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout
    return float(out.strip())


def extract_frame(video, t, out):
    if not os.path.exists(out):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", video, "-frames:v", "1", out], check=True)
    return out


def _units(s):
    return sum(0.55 if ord(c) < 128 else 1.0 for c in s)


def phrases(transcript_json, replace=None, drop_after=None, max_units=13.5):
    """把转写结果按标点切成短句字幕：[(start, end, text)]；过长的句子在词边界处对半切开。"""
    import re
    data = json.load(open(transcript_json, encoding="utf-8"))
    groups = []  # 每组: [(start, end, piece)]
    for s in data:
        if drop_after is not None and s["start"] >= drop_after:
            continue
        cur = []
        for w in s["words"]:
            word = w["word"].strip()
            cur.append((w["start"], w["end"], re.sub(r"[,，。!！?？]", "", word).replace("、", " ")))
            if re.search(r"[,，。!！?？]$", word):
                groups.append(cur)
                cur = []
        if cur:
            groups.append(cur)

    def text_of(g):
        return "".join(p for _, _, p in g).strip()

    def word_bounds(g):
        """jieba 分词后词与词之间的位置(按片段下标)，只允许在这些位置断句，避免把「减少」切成「减 / 少」。"""
        try:
            import jieba
            jieba.setLogLevel(60)
        except ImportError:
            return None
        full = "".join(p for _, _, p in g)
        cuts, n = set(), 0
        for w in jieba.lcut(full):
            n += len(w)
            cuts.add(n)
        out, n = set(), 0
        for i, (_, _, p) in enumerate(g):
            if n in cuts:
                out.add(i)
            n += len(p)
        return out

    def split(g):
        if _units(text_of(g)) <= max_units or len(g) < 2:
            return [g]
        bounds = word_bounds(g)
        best, best_i = None, None
        for i in range(1, len(g)):
            a, b = g[i - 1][2], g[i][2]
            if a and b and a[-1].isascii() and a[-1].isalnum() and b[0].isascii() and b[0].isalnum():
                continue  # 不在英文单词中间切
            if bounds is not None and i not in bounds:
                continue  # 不在中文词中间切
            d = abs(_units(text_of(g[:i])) - _units(text_of(g[i:])))
            if best is None or d < best:
                best, best_i = d, i
        if best_i is None:
            return [g]
        return split(g[:best_i]) + split(g[best_i:])

    out = []
    for g in groups:
        for part in split(g):
            out.append([part[0][0], part[-1][1], text_of(part)])
    if replace:
        for p in out:
            for a, b in replace:
                p[2] = p[2].replace(a, b)
    return out
