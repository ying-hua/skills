"""用 faster-whisper 转写配音，输出带词级时间戳的 JSON 和 SRT。

用法: python tools/transcribe.py <audio> <out_prefix> [model]
"""
import json
import os
import sys

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
from faster_whisper import WhisperModel

audio, out_prefix = sys.argv[1], sys.argv[2]
model_name = sys.argv[3] if len(sys.argv) > 3 else "medium"

model = WhisperModel(model_name, device="cpu", compute_type="int8")
segments, info = model.transcribe(
    audio, language="zh", word_timestamps=True, vad_filter=False,
    initial_prompt="以下是普通话的句子，介绍一个AI工具和GitHub开源项目。",
)

result = []
for s in segments:
    result.append({
        "start": s.start, "end": s.end, "text": s.text.strip(),
        "words": [{"start": w.start, "end": w.end, "word": w.word} for w in (s.words or [])],
    })

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
