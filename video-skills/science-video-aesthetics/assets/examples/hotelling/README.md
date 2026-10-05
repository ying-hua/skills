# 示例：《为什么两家奶茶店总开在隔壁》（霍特林定律，160 秒）

"世界式"讲解的完整参考实现，配合 `../../../references/worldbuilding.md` 阅读。可学习思路和画法，外观适合主题时也可直接沿用。

- `gfx.py`：缓动、`Track` 关键帧轨道、cairo 图元、PIL 文字转 cairo（带缓存）、胶囊标签 `pill`
- `world.py`：俯视沙滩世界（海浪、泡沫、闪光、伞、人、棕榈、卷尺、冰淇淋车、HSL 染色地盘、头顶徽章）
- `street.py`：正视街景、选民直方图、手机形态插值
- `story.py`：时间线（车 / 镜头轨道、字幕、气泡、增减数字、印章、卡片、条纹转场）+ 日夜调色 / 暗角 / 颗粒后期
- `render.py`：`--stills` 联系表 / `--chunk i n` 分段渲染
- `audio.py`：合成音效 + 环境声底 + 自动"改选啵声"，叠在 `../bgm.mp3` 下

运行：`python render.py --stills 0,20,68.8 --sheet out/s.png`；分段渲染 `python render.py --chunk 0 4`（16 GB 内存最多并行 3–5 个）。
依赖 Windows 字体 STHUPO（华文琥珀）、msyhbd、Rubik-Bold；其他系统需改 `gfx.py` 顶部字体路径。
