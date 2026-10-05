---
name: science-video-kit
description: 用纯 Python 程序化制作几分钟长、画面惊艳的中文科普 / 讲解短视频：cairo/numpy 2D 或 moderngl GPU 画面、合成音效与配乐（也可用用户提供的 BGM）、ffmpeg 压制。提供可复用的基础设施（中英混排字幕、泛光/颗粒后期、GPU 渲染框架、可续渲的并行分段渲染、BGM 结构分析、音效与乐器库、响度标准化的上传压制、不看图的数值质检），并用风格目录 + 本地风格日志强制每个视频的画面和声音都不雷同。适用于“做一个关于 X 的科普视频 / 宣传片 / 动画讲解”。
compatibility: "Requires Python 3.9+ with numpy, scipy, pycairo, opencv-python (cv2) and Pillow; ffmpeg and ffprobe on PATH. GPU path additionally needs moderngl and an OpenGL 4.3 capable GPU. Fonts default to Windows paths (Noto Serif/Sans SC, Georgia) and fall back to fc-match / common CJK fonts on Linux and macOS; set fonts per project with vk_core.set_fonts."
---

# Science video kit

**每次都要让用户惊艳**：基础设施共享，风格绝不复用。
`scripts/` 只是工具箱，每个视频的视觉语言都要根据主题从零设计。

开工前先读：
- `references/styles.md`：风格菜单，以及防雷同规则（本地 `STYLE_LOG.md`）。
- `references/quality.md`：惊艳标准和开场钩子规则。
- `references/pitfalls.md`：已经踩过的坑。

## 使用前需提供什么

- **主题**：一句话即可，例如“三个枪手决斗，枪法最差的那个为什么活得最久”。
- **可选：BGM 文件**的本地路径。不提供时由 agent 自己合成配乐。
- **可选**：目标时长、横屏或竖屏（默认 1920×1080）、目标文件大小（默认约 130 MB）、视频工作区目录。
- 本 skill **不附带任何素材**，所有画面和声音都在本地由代码生成。用户的 `STYLE_LOG.md`、
  渲染结果和 BGM 都留在用户本地，不要放进本仓库。

## 工作流程（括号内是 token 预算）

**0. 准备（很省）**
- 在用户的视频工作区新建 `<项目>/`，把 `scripts/*.py` 和 `assets/templates/*.py` 复制进去。项目自包含，副本可以随便改。
- 读取或创建工作区根目录的 `STYLE_LOG.md`（记录已交付视频的风格）。
- 用 `vk_core.set_fonts(...)` 选好字体搭配。

**1. 先做内容（不渲染）**
- 把数学或物理算准：在代码里精确计算（分数、真实模拟）并 `assert`。画面上的每个数字都要来自这些代码。
- 写成带时间的字幕脚本：50 px 字号下每行不超过约 22 个汉字，每行停留 2.5–4 秒。
- 结构：钩子（≤ 15 秒）→ 规则或背景 → 直觉 → 反转 → 可视化证明 → 独立验证（模拟或实验）→ 结论 → 结尾提问。
- 如果用户提供了 BGM，先运行 `python vk_bgm.py <bgm>`，把段落边界对齐到它找出的 HITS、QUIET、SILENCES：
  - 高潮对应揭晓；
  - 安静段落对应反思和反转；
  - 片尾前的静音对应戏剧性停顿。
- 如果没有 BGM，就在 `audio.py` 里写配乐，曲风要和 `STYLE_LOG.md` 里的都不同。固定 BPM，让小节线落在段落开头。

**2. 风格发散**
- 提出 3 个彼此差异很大的方向，参考 `references/styles.md` 并结合主题自身的意象，按其中的规则排除雷同。
- 选定一个，把决策写在 `scenes.py` 顶部：配色常量、`set_fonts`、`set_tags`。

**3. 主视觉关口（2–3 张图）**
- 只做两张主视觉帧：第 0 帧钩子，加上招牌可视化。
- 运行 `python vk_render.py sheet --times 0,<t> --out out/look.png`，看一次。
- 对照 `quality.md` 判断。不惊艳就在这一步换方向，这时改动代价最小。

**4. 搭建各段**
- 写完所有段落，然后**只用联系表**检查：`vk_render.py sheet --times ...`，每张 8–12 格、每格 960 px，大约每 2–3 段看一张。
- 联系表上发现的问题，全部在正式渲染前修好。
- 不要逐帧看单张图，也不要直接读取渲染出的 mp4。

**5. 渲染和声音同时进行**
- 后台运行 `python vk_render.py render --workers 5`。16 GB 内存最多 5 个进程；GPU 渲染用 `--workers 1`。
- 渲染期间写音效 cue，运行 `python audio.py` 生成音轨。
- 用 `tail` 轮询渲染日志。

**6. 不看图的质检**
- `python vk_scan.py spikes out/chunks/*.mp4` 必须报告 0 个可疑帧。
- 检查音频每秒的电平数值。
- `python vk_finalize.py --out out/<name>.mp4` 生成约 130 MB、-14 LUFS 的成片。
- 用 `vk_scan.py sheet` 从成片抽 6 帧拼图，看一次。
- 删除分段和 `video_noaudio.mp4`，只交付上传版。

**7. 收尾**
- 在 `STYLE_LOG.md` 追加这次的风格：渲染、配色、字体、动效、音乐、招牌画面。
- 如实告诉用户哪些检查过、哪些没有。例如“音频只看了电平数据，没有试听”。

## 脚本一览（scripts/）

| 文件 | 内容 |
|---|---|
| `vk_core.py` | **画布**：`Canvas`（cairo 底层 + 半分辨率加色发光层 `cv.g`，用于泛光），`set_cam` 缩放/平移/旋转/震动。<br>**辅助**：缓动 `ss/ease_out/ease_io/back_out`，`win()` 显隐窗口，`hrand` 确定性哈希，`fbm` 噪声，`to_surface`/`paint_img` 贴 numpy 纹理。<br>**特效**：`tracer` 弹道、`muzzle` 枪口闪光、`impact` 尘土冲击、`dust_motes` 尘埃、`reticle` 准星、`dashed_line`、`arrow_head`、`rrect`、`panel`。<br>**文字**：`add_text(cv, '[k]彩色[/] 标记', x, y, size, t=, anim='rise'/'type'/None, scale=, glow=)`，中英混排，`set_fonts`，`set_tags`。<br>**后期**：`finish(cv, idx)`（泛光、文字、闪白、高光压缩、色差、暗角、颗粒、淡出） |
| `vk_gl.py` | 无头 moderngl 框架：抖动多采样累积 + 快门运动模糊，带 NaN/Inf 保护的 resolve，mip 泛光，ACES，调色，分条渲染防 TDR，`look_at`，`project`（3D 坐标转屏幕坐标，用于贴标签）。着色器约定见文件头注释 |
| `vk_render.py` | `sheet` 联系表 · `render` 并行可续渲分段（`--from/--to` 只重渲某个时间段）· `concat` |
| `vk_audio.py` | 约 35 种音效；乐器 `fm_bell`、`pluck`（Karplus-Strong）、`supersaw`、`pad`、`kick/snare/hat`、`marimba`、`epiano`、`sub`；`reverb`、`echo`、`pingpong`、`Bus`、`render_cues`、`click_rain`（一个模拟事件一声）、`load_bgm`、`duck`、`master` |
| `vk_bgm.py` | BGM 结构分析：速度、逐秒电平、HITS / QUIET / SILENCES |
| `vk_scan.py` | `spikes`（闪帧、NaN 黑块）、`levels`、成片抽帧 `sheet` |
| `vk_finalize.py` | loudnorm 响度标准化 + 两遍 x264，压到 `--mb` 指定的大小 |

模板 `assets/templates/`：
- `scenes.py`：Section 分段模式、`cap` 字幕、第 0 帧可见的 `stamp` 标题、cue 列表、`render_frame`。
- `audio.py`：外部 BGM 或自写配乐、压低音乐、母带处理。

竖屏视频：导入 `vk_core` 前设置环境变量 `VK_W=1080 VK_H=1920`。

## 省 token 的纪律

- 制作期间唯一的看图方式是 8–12 格的联系表，每张约 1.5k token。一个视频大约需要 6–8 张，外加成片 1 张。
- 能用数字就不用图：`vk_scan` 的 spikes/levels、音频电平输出、代码里的数学断言。
- 长时间渲染放后台，用 `tail` 轮询，不要整段读取日志或视频。
- 大文件用文件写入工具一次写完。
- 用户报告某个时间点有问题时，只对那一段做联系表（比如 2 秒内取 6 格），再用 `--from/--to` 只重渲那几段。

## 自测

```bash
python tests/test_kit.py
```
