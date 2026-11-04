"""配音质检：逐 0.25s 估基频(自相关)，标出音高异常(疑似变女声)和长静音。
用法: python tools/voice_check.py a.mp3 [b.mp3 ...]"""
import sys, subprocess, numpy as np
SR = 16000
def load(p):
    raw = subprocess.run(['ffmpeg','-v','error','-i',p,'-ac','1','-ar',str(SR),'-f','s16le','-'],capture_output=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32)/32768
def f0(fr):
    fr = fr - fr.mean()
    if np.sqrt((fr**2).mean()) < 0.02: return None
    ac = np.correlate(fr, fr, 'full')[len(fr)-1:]
    lo, hi = SR//400, SR//70
    k = lo + np.argmax(ac[lo:hi])
    return SR/k if ac[k] > 0.35*ac[0] else None
for p in sys.argv[1:]:
    x = load(p); hop = SR//20; win = int(SR*0.04)
    ts, fs = [], []
    for i in range(0, len(x)-win, hop):
        v = f0(x[i:i+win]); ts.append(i/SR); fs.append(v)
    voiced = np.array([v for v in fs if v])
    med = np.median(voiced)
    # 0.5s 窗口内浊音中位数 > 1.45×整体中位数 → 可疑
    sus = []
    for j in range(len(fs)):
        seg = [v for v in fs[j:j+10] if v]
        if len(seg) >= 5 and np.median(seg) > 1.45*med: sus.append(round(ts[j],2))
    # 静音段
    rms = np.array([np.sqrt((x[i:i+hop]**2).mean()) for i in range(0,len(x)-hop,hop)])
    sil, start = [], None
    for j,r in enumerate(rms):
        if r < 0.01 and start is None: start = j
        if r >= 0.01 and start is not None:
            if (j-start)*0.05 >= 0.35: sil.append((round(start*0.05,2), round((j-start)*0.05,2)))
            start = None
    print(f'{p[-60:]}\n  dur={len(x)/SR:.2f}s medF0={med:.0f}Hz  可疑高音起点={sus[:20]}\n  静音(起点,长度)={sil}')
