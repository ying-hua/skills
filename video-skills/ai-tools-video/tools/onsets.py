"""从配音响度里找音节起点，用来把片头文字(一天一个/超实用的/网站/第N期)对齐到真实发音。

剪映 SRT 只有句级时间，句内逐字是均分估的；片头这种每个词都要卡点的地方用这里的结果。
用法: python tools/onsets.py <audio> <t0> <t1>   打印 t0~t1 的音节起点和响度曲线
"""
import subprocess
import sys

import numpy as np

SR, HOP = 16000, 160  # 10ms 一帧


def loudness(audio):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", audio, "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                         capture_output=True).stdout
    x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    n = (len(x) - 400) // HOP
    e = np.array([np.sqrt(np.mean(x[i * HOP:i * HOP + 400] ** 2)) for i in range(n)])
    return 20 * np.log10(e + 1e-6)


def onsets(audio, t0, t1, rise=6.0, floor=-30.0, min_gap=0.12, _cache={}):
    """音节起点(秒)：响度从局部低谷回升 rise dB 以上且超过 floor；起点取低谷后第一次明显出声(>低谷+3dB 且 >-45dB)的帧。"""
    if audio not in _cache:
        _cache[audio] = loudness(audio)
    db = _cache[audio]
    i0, i1 = int(t0 * 100), min(int(t1 * 100), len(db) - 1)
    out, lo, lo_i = [], db[i0], i0
    i = i0 + 1
    while i < i1:
        if db[i] < lo:
            lo, lo_i = db[i], i
        if db[i] > floor and db[i] - lo >= rise:
            j = next(k for k in range(lo_i, i + 1) if db[k] > max(lo + 3, -45))
            t = round(j / 100, 2)
            if not out or t - out[-1] >= min_gap:
                out.append(t)
            while i + 1 < i1 and db[i + 1] >= db[i]:
                i += 1
            lo, lo_i = db[i], i
        i += 1
    return out


def snap(audio, t, window=0.15):
    """把估计时间 t 吸附到最近的音节起点(±window 内没有就原样返回)。"""
    on = onsets(audio, t - window, t + window)
    return min(on, key=lambda x: abs(x - t)) if on else t


def opening_times(transcript_json, audio):
    """片头 OPEN 时间点：在 transcript 里找「一天一个 / 超 / 网 / 第 / 今」的估计时间，再吸附到真实音节起点。"""
    import json
    words = [w for s in json.load(open(transcript_json, encoding="utf-8")) for w in s["words"]]
    chars = [(w["start"], w["word"].strip()) for w in words]
    text = "".join(c for _, c in chars)

    def at(sub, after=0):
        k = text.index(sub, after)
        n = 0
        for t, c in chars:
            if n >= k:
                return t, k
            n += len(c)

    yi, k = at("一天一个")
    chao, k = at("超", k)
    wang, k = at("网", k)
    di, k = at("第", k)
    card, k = at("今天", k)
    r = dict(t_yi=yi, t_chao=chao, t_wang=wang, t_di=di, t_card=card)
    return {n: snap(audio, t) for n, t in r.items()}


if __name__ == "__main__":
    audio, t0, t1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
    print("起点:", onsets(audio, t0, t1))
