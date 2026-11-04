"""封面(仿照往期 图片1 / 图片2 的版式)：一天一个 超实用的网站 + Vol 标签 + 虚线框截图 + 底部一句话。"""
import os

from PIL import Image, ImageDraw, ImageFont

import fx

YELLOW = (255, 192, 0)


def _font(size, weight="Regular"):
    f = ImageFont.truetype(os.path.join(fx.FONT_DIR, "NotoSansSC-VF.ttf"), size)
    try:
        f.set_variation_by_name(weight)
    except Exception:
        pass
    return f


def _dashed_rrect(d, box, r, color, width, dash=46, gap=26):
    path = fx._rrect_path(*box, r, step=1.0)
    L = 0.0
    for i in range(len(path) - 1):
        if (L % (dash + gap)) < dash:
            d.line([tuple(path[i]), tuple(path[i + 1])], fill=color, width=width)
        L += 1.0


def make_cover(ep, shot_path, bottom_white, bottom_yellow, out, size=(908, 1181)):
    W, H = size
    ss = 2
    img = Image.new("RGB", (W * ss, H * ss), (0, 0, 0))
    d = ImageDraw.Draw(img)
    u = W * ss / 908  # 以 908 宽为基准的缩放
    if W > H:
        u = H * ss / 1181 * 1.08

    # 标题两行
    f1 = _font(int((118 if W <= H else 150) * u), "Regular")
    y = int(40 * u)
    d.text((W * ss / 2 - int(40 * u), y), "一天一个", font=f1, fill=(255, 255, 255), anchor="mt")
    y2 = y + int((128 if W <= H else 150) * u)
    left, right = "超实用的 ", "网站"
    lw, rw = d.textlength(left, font=f1), d.textlength(right, font=f1)
    x0 = W * ss / 2 - (lw + rw) / 2
    d.text((x0, y2), left, font=f1, fill=(255, 255, 255))
    d.text((x0 + lw, y2), right, font=f1, fill=YELLOW)

    # Vol 标签
    fv = _font(int(56 * u), "Black")
    label = f"Vol.{ep:03d}"
    tw = d.textlength(label, font=fv)
    pw, ph = int(tw + 70 * u), int(100 * u)
    pill = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    pd = ImageDraw.Draw(pill)
    pd.rounded_rectangle((0, 0, pw - 1, ph - 1), ph // 2, fill=YELLOW + (255,))
    pd.text((pw / 2, ph / 2), label, font=fv, fill=(0, 0, 0), anchor="mm")
    pill = pill.rotate(-14, expand=True, resample=Image.BICUBIC)
    img.paste(pill, (int(W * ss - pill.width - 30 * u), int(25 * u)), pill)

    # 虚线框 + 截图
    fy0 = y2 + int(185 * u)
    bottom_h = int(200 * u)
    fy1 = H * ss - bottom_h
    fx0, fx1 = int(18 * u), W * ss - int(18 * u)
    shot = Image.open(shot_path).convert("RGB")
    bw, bh = fx1 - fx0 - int(52 * u), fy1 - fy0 - int(52 * u)
    s = min(bw / shot.width, bh / shot.height)
    shot = shot.resize((int(shot.width * s), int(shot.height * s)), Image.LANCZOS)
    fy1 = fy0 + shot.height + int(52 * u)
    _dashed_rrect(d, (fx0, fy0, fx1, fy1), int(40 * u), YELLOW, int(11 * u), dash=int(46 * u), gap=int(26 * u))
    img.paste(shot, ((W * ss - shot.width) // 2, fy0 + int(26 * u)))

    # 底部一句话
    fb = _font(int(110 * u), "Black")
    by = fy1 + int(40 * u)
    lw, rw = d.textlength(bottom_white, font=fb), d.textlength(bottom_yellow, font=fb)
    x0 = W * ss / 2 - (lw + rw) / 2
    d.text((x0, by), bottom_white, font=fb, fill=(255, 255, 255))
    d.text((x0 + lw, by), bottom_yellow, font=fb, fill=YELLOW)

    # 底部留白裁掉
    img = img.crop((0, 0, W * ss, min(H * ss, by + int(160 * u))))
    canvas = Image.new("RGB", (W * ss, H * ss), (0, 0, 0))
    canvas.paste(img, (0, (H * ss - img.height) // 2))
    canvas.resize((W, H), Image.LANCZOS).save(out)
    return out
