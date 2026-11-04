"""把剪映「智能字幕」导出的 SRT 转成 transcribe.py 同格式的 transcript.json/.srt（替代 Whisper）。

剪映只给句级时间，这里按字数把每句时长均分到每个字（中文 1 份，英文单词按字母数折算），
逐字时间误差约 ±0.15s，够定镜头切点用。句尾补逗号，jy.phrases 会按句切字幕。

用法: python tools/srt_import.py <剪映导出.srt> <out_prefix>
"""
import json
import re
import sys


def parse_srt(path):
    data = open(path, "rb").read()
    try:
        raw = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raw = data.decode("gbk")
    raw = raw.replace("\r\n", "\n")
    cues = []
    for block in re.split(r"\n\s*\n", raw.strip()):
        lines = [l for l in block.split("\n") if l.strip()]
        m = next((re.match(r"(\S+)\s*-->\s*(\S+)", l) for l in lines if "-->" in l), None)
        if not m:
            continue
        text = " ".join(lines[[i for i, l in enumerate(lines) if "-->" in l][0] + 1:]).strip()
        cues.append((sec(m.group(1)), sec(m.group(2)), text))
    return cues


def sec(t):
    h, m, s = t.replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def tokens(text):
    # 英文/数字连成一个词，中文逐字，标点并到前一个字上
    out = []
    for tok in re.findall(r"[A-Za-z0-9][A-Za-z0-9.\-_+']*|\S", text):
        if re.fullmatch(r"[,，。!！?？、:：;；\"'“”‘’()（）]", tok) and out:
            out[-1] = out[-1] + tok
        else:
            out.append(tok)
    return out


def weight(tok):
    core = re.sub(r"[^\w]", "", tok)
    return max(1.0, len(core) * 0.4) if core.isascii() else 1.0


src, out_prefix = sys.argv[1], sys.argv[2]
result = []
for start, end, text in parse_srt(src):
    toks = tokens(text)
    if not toks:
        continue
    if not re.search(r"[,，。!！?？]$", toks[-1]):
        toks[-1] += ","
    total = sum(weight(t) for t in toks)
    t, words = start, []
    for i, tok in enumerate(toks):
        nt = end if i == len(toks) - 1 else t + (end - start) * weight(tok) / total
        prefix = " " if tok[0].isascii() and tok[0].isalnum() and i > 0 else ""
        words.append({"start": round(t, 3), "end": round(nt, 3), "word": prefix + tok})
        t = nt
    result.append({"start": start, "end": end, "text": "".join(w["word"] for w in words).strip(), "words": words})

with open(out_prefix + ".json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=1)


def ts(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


with open(out_prefix + ".srt", "w", encoding="utf-8") as f:
    for i, s in enumerate(result, 1):
        f.write(f"{i}\n{ts(s['start'])} --> {ts(s['end'])}\n{s['text']}\n\n")

for s in result:
    print(f"[{s['start']:6.2f}-{s['end']:6.2f}] {s['text']}")
