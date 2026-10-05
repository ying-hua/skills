---
name: science-video-kit
description: 程序化制作中文讲解 / 科普视频的 Python 工具箱：cairo/numpy 2D 画布与相机、中英混排字幕、泛光/颗粒后期、moderngl GPU 渲染框架、可续渲的并行分段渲染与联系表、BGM 结构分析、音效与乐器合成库、不看图的数值质检（闪帧/黑块/电平）、响度标准化的上传压制。只提供工具和用法，不含创意、风格或叙事建议。适用于需要用代码渲染视频画面和声音的项目。
compatibility: "Requires Python 3.9+ with numpy, scipy, pycairo, opencv-python (cv2) and Pillow; ffmpeg and ffprobe on PATH. GPU path additionally needs moderngl and an OpenGL 4.3 capable GPU. Fonts default to Windows paths (Noto Serif/Sans SC, Georgia) and fall back to fc-match / common CJK fonts on Linux and macOS; set fonts per project with vk_core.set_fonts."
---

# Science video kit

纯工具箱：画布、渲染、音频、质检、压制。画面内容、风格和叙事由使用者决定，本 skill 不做建议。

技术上的已知问题见 `references/pitfalls.md`。

## 使用前需提供什么

- 要做的视频内容（场景代码由 agent 按用户需求编写）。
- **可选：BGM 文件**的本地路径。
- **可选**：分辨率（默认 1920×1080）、目标文件大小（默认约 130 MB）、视频工作区目录。
- 本 skill **不附带任何素材**。渲染结果和 BGM 都留在用户本地，不要放进本仓库。

## 用法

**0. 建项目**
- 在视频工作区新建 `<项目>/`，把 `scripts/*.py` 和 `assets/templates/*.py` 复制进去。项目自包含，副本可以随便改。
- 用 `vk_core.set_fonts(...)` 设置字体。
- 竖屏：导入 `vk_core` 前设置环境变量 `VK_W=1080 VK_H=1920`。

**1. 场景代码**（`scenes.py`）
- 契约：`TOTAL`（秒）和 `render_frame(t, idx)`，返回 RGB uint8 帧。
- 模板提供 `Section` 分段、`cap` 字幕、`stamp` 缩放入场标题、cue 列表、`render_frame`。
- 有 BGM 时可先运行 `python vk_bgm.py <bgm>`，得到速度、逐秒电平、HITS / QUIET / SILENCES 时间点。

**2. 联系表检查**
- `python vk_render.py sheet --times 0,12.5,30 --out out/look.png`：把指定时刻的帧拼成一张图。
- 每张 8–12 格、每格 960 px 最省 token；不要逐帧看单张图，也不要直接读取渲染出的 mp4。

**3. 渲染（后台）**
- `python vk_render.py render --workers 5`：并行分段渲染，可续渲；`--from/--to` 只重渲某个时间段。
- 16 GB 内存最多 5 个进程（同机还有其他渲染任务时更少）；GPU 渲染用 `--workers 1`。
- 长时间渲染放后台，用 `tail` 轮询日志。

**4. 音频**
- 模板 `audio.py`：按场景 cue 渲染音效，叠加外部 BGM 或自写配乐，压低音乐（`duck`），母带处理。`python audio.py` 生成 `out/soundtrack.wav`。

**5. 质检与压制**
- `python vk_scan.py spikes out/chunks/*.mp4`：报告闪帧、NaN 黑块等可疑帧。
- `python vk_scan.py levels out/soundtrack.wav`：音频逐秒电平。
- `python vk_finalize.py --out out/<name>.mp4`：loudnorm −14 LUFS + 两遍 x264，压到 `--mb` 指定大小。
- `python vk_scan.py sheet <成片> 5,40,90 [out.png]`：从成片指定时刻抽帧拼图。
- 交付后可删除分段和 `video_noaudio.mp4`。

## 脚本一览（scripts/）

| 文件 | 内容 |
|---|---|
| `vk_core.py` | **画布**：`Canvas`（cairo 底层 + 半分辨率加色发光层 `cv.g`，用于泛光），`set_cam` 缩放/平移/旋转/震动。<br>**辅助**：缓动 `ss/ease_out/ease_io/back_out`，`win()` 显隐窗口，`hrand` 确定性哈希，`fbm` 噪声，`to_surface`/`paint_img` 贴 numpy 纹理。<br>**特效**：`tracer` 弹道、`muzzle` 枪口闪光、`impact` 尘土冲击、`dust_motes` 尘埃、`reticle` 准星、`dashed_line`、`arrow_head`、`rrect`、`panel`。<br>**文字**：`add_text(cv, '[k]彩色[/] 标记', x, y, size, t=, anim='rise'/'type'/None, scale=, glow=)`，中英混排，`set_fonts`，`set_tags`。<br>**后期**：`finish(cv, idx)`（泛光、文字、闪白、高光压缩、色差、暗角、颗粒、淡出） |
| `vk_gl.py` | 无头 moderngl 框架：抖动多采样累积 + 快门运动模糊，带 NaN/Inf 保护的 resolve，mip 泛光，ACES，调色，分条渲染防 TDR，`look_at`，`project`（3D 坐标转屏幕坐标，用于贴标签）。着色器约定见文件头注释 |
| `vk_render.py` | `sheet` 联系表 · `render` 并行可续渲分段（`--from/--to` 只重渲某个时间段）· `concat` |
| `vk_audio.py` | 约 35 种音效；乐器 `fm_bell`、`pluck`（Karplus-Strong）、`supersaw`、`pad`、`kick/snare/hat`、`marimba`、`epiano`、`sub`；`reverb`、`echo`、`pingpong`、`Bus`、`render_cues`、`click_rain`（一个事件一声）、`load_bgm`、`duck`、`master` |
| `vk_bgm.py` | BGM 结构分析：速度、逐秒电平、HITS / QUIET / SILENCES |
| `vk_scan.py` | `spikes`（闪帧、NaN 黑块）、`levels`、成片抽帧 `sheet` |
| `vk_finalize.py` | loudnorm 响度标准化 + 两遍 x264，压到 `--mb` 指定的大小 |

模板 `assets/templates/`：`scenes.py`（分段、字幕、标题、cue、`render_frame`）、`audio.py`（外部 BGM 或自写配乐、压低音乐、母带处理）。

## 省 token 的纪律

- 看图只用联系表，每张约 1.5k token。
- 能用数字就不用图：`vk_scan` 的 spikes/levels、音频电平输出、代码里的断言。
- 长时间渲染放后台，用 `tail` 轮询，不要整段读取日志或视频。
- 用户报告某个时间点有问题时，只对那一段做联系表（比如 2 秒内取 6 格），再用 `--from/--to` 只重渲那几段。

## 自测

```bash
python tests/test_kit.py
```
