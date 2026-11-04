"""用用户的「片头2」预设生成片头：一天一个 / 超实用的 / 网站 / 第N期 → 项目卡片 + 项目名 + 震惊贴纸 + 音效。"""
import os

from PIL import Image

import preset as P

CARD_SIZE = (1368, 802)  # 片头2 里 page.png 的尺寸，保持同比例布局不变


def make_card_image(src_png, box, out):
    """从截图裁出 box，按片头2卡片的比例(1368x802)输出。"""
    im = Image.open(src_png).convert("RGB").crop(box)
    im.resize(CARD_SIZE, Image.LANCZOS).save(out)
    return out


def _replace_photo(card_png):
    def edit(entry):
        for v in entry["draft"]["materials"].get("videos", []):
            if v.get("type") == "photo":
                v["path"] = card_png.replace("\\", "/")
                v["material_name"] = os.path.basename(card_png)
                v["width"], v["height"] = CARD_SIZE
    return edit


TYPE_SRC = (12 / 30, 34 / 30)  # 打字声保留的素材区间(秒)
DI_LEAD = 0.333  # 片头3「第N期」入场动画(向左滑动)时长


def add_opening(T, ep, name, card_png, t_yi, t_chao, t_wang, t_di, t_card, t_end):
    """各时间点(秒)：一天一个 / 超实用的 / 网站 / 第N期 / 今天分享的是(卡片) / 卡片结束。"""
    op = P.Preset("片头2")
    T.element(op, "一天一个", t_yi, t_card - t_yi, group="片头文字")
    T.element(op, "超实用的", t_chao, t_card - t_chao, group="片头文字")
    T.element(op, "网站", t_wang, t_card - t_wang, group="片头文字")
    T.element(op, "第26期", t_di, t_card - t_di, group="片头文字", text=f"第{ep}期")
    T.element(op, "复合片段8", t_card, t_end - t_card, group="片头卡片", edit_combo=_replace_photo(card_png))
    T.element(op, "EdClub", t_card, t_end - t_card, group="片头文字", text=name)
    T.element(op, "综艺震惊惊讶情绪", t_card + 0.3, t_end - t_card - 0.3, group="片头贴纸")
    # 音效节奏(用户 2026-10-07 校正，30fps 计)：
    # 打字声 前 12 帧是静音 → 截掉，和文字同时出；第 34 帧之后太长 → 截掉
    # 提示音 前 8 帧是静音，但「第N期」本身有入场动画，所以带着静音和文字开头对齐刚好
    T.sound(op, "打字声", t_yi, src_start=TYPE_SRC[0], max_dur=TYPE_SRC[1] - TYPE_SRC[0])
    T.sound(op, "回答正确", t_wang + 0.1)
    T.sound(op, "提示音", t_di)
    T.sound(op, "打字声", t_card, src_start=TYPE_SRC[0], max_dur=TYPE_SRC[1] - TYPE_SRC[0])
    return op


def _shift_keyframes(seg, new_t1):
    """预设里「卡片出现时字往上让位」的那组关键帧(相对片段开头)整体平移，让最后一帧落在 new_t1(秒)。"""
    kfs = seg.get("common_keyframes", [])
    t1 = max((k["time_offset"] for kf in kfs for k in kf["keyframe_list"]), default=None)
    if t1 is None:
        return
    d = P.us(new_t1) - t1
    for kf in kfs:
        for k in kf["keyframe_list"]:
            k["time_offset"] = max(0, k["time_offset"] + d)


def add_opening3(T, ep, name, card_png, t_shiyong, t_di, t_card, t_end):
    """「片头3」(2026-10-13 用户重做，参考小W)：实用工具(居中砸出) → 第N期(胶囊滑入) →
    今天分享的是：两行字一起上移让位，项目卡片转入 + 项目名弹出。

    预设本身有背景复合片段和配音，这里都不用(背景用「1分钟背景」，配音是草稿主音轨)。
    音效相对文字的偏移照预设：回答正确=实用工具，提示音=第N期+0.267s，唰=卡片。
    t_di 传配音里「第」的音节起点：文字会提前 DI_LEAD 出现，让「向左滑动」入场动画刚好在念到「第N期」时结束
    (用户 2026-10-14 第34期反馈：动画结束才算出现，原来卡在起点显得晚)。让位关键帧仍和「实用工具」对齐在 t_card。
    """
    op = P.Preset("片头3")
    s, _ = T.element(op, "实用工具", t_shiyong, t_end - t_shiyong, group="片头文字")
    _shift_keyframes(s, t_card - t_shiyong)
    t_di = max(t_shiyong + 0.2, t_di - DI_LEAD)
    s, _ = T.element(op, "第33期", t_di, t_end - t_di, group="片头文字", text=f"第{ep}期")
    _shift_keyframes(s, t_card - t_di)
    T.element(op, "复合片段8", t_card, t_end - t_card, group="片头卡片", ttype="video",
              edit_combo=_replace_photo(card_png))
    T.element(op, "EdClub", t_card, t_end - t_card, group="片头文字", text=name)
    T.sound(op, "回答正确", t_shiyong, volume=0.39)
    T.sound(op, "提示音", t_di + 0.267, volume=0.57)
    T.sound(op, "唰", t_card, volume=0.47)
    return op


def add_opening_short(T, ep, name, card_png, t_start, lines, t_di, t_card, t_end, text_y=(0.55, 0.25)):
    """短口号版片头(2026-10-12 用户定)：不说「一天一个」，项目卡片从口号一开始就在画面里。

    lines：[(文字, 出现时间)]，最多两行，第一行用预设「超实用的」样式(白)，第二行用「网站」样式(黄色大字)；
    只有一行时用「网站」样式。例：[("超实用的", t1), ("网站", t2)] 或 [("实用工具", t1)]。
    text_y：两行文字的纵向位置(剪映坐标，上正)，整体上移给卡片腾位置。
    """
    op = P.Preset("片头2")
    T.element(op, "复合片段8", t_start, t_end - t_start, group="片头卡片", edit_combo=_replace_photo(card_png))
    styles = ["超实用的", "网站"] if len(lines) == 2 else ["网站"]
    ys = text_y if len(lines) == 2 else text_y[1:]
    for (text, t), style, y in zip(lines, styles, ys):
        s, _ = T.element(op, style, t, t_card - t, group="片头文字", text=text)
        s["clip"]["transform"]["y"] = y
        if style == "网站" and len(text) > 2:  # 「网站」样式按两个字设计，字多了按比例缩小，免得超出画面
            f = 2.2 / len(text)
            s["clip"]["scale"] = {"x": s["clip"]["scale"]["x"] * f, "y": s["clip"]["scale"]["y"] * f}
    T.element(op, "第26期", t_di, t_card - t_di, group="片头文字", text=f"第{ep}期")
    T.element(op, "EdClub", t_card, t_end - t_card, group="片头文字", text=name)
    T.element(op, "综艺震惊惊讶情绪", t_card + 0.3, t_end - t_card - 0.3, group="片头贴纸")
    T.sound(op, "打字声", t_start, src_start=TYPE_SRC[0], max_dur=TYPE_SRC[1] - TYPE_SRC[0])
    if len(lines) == 2:
        T.sound(op, "回答正确", lines[1][1] + 0.1)
    T.sound(op, "提示音", t_di)
    T.sound(op, "打字声", t_card, src_start=TYPE_SRC[0], max_dur=TYPE_SRC[1] - TYPE_SRC[0])
    return op
