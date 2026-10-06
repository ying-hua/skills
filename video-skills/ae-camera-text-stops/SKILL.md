---
name: ae-camera-text-stops
description: 使用 After Effects JSX 为录屏或文字视频制作可编辑的 2.5D 摄像机运镜：停住读字、快速换位、位置与目标点同步平移、光标连续滑动。适用于 AE 三机位运镜、文字聚焦、摄像机停顿、上下视角修正、录屏加减速、黑屏排查以及导出 AEP/MP4。优先脚本，不逐个手动拖关键帧。
compatibility: "Requires Windows/PowerShell, Adobe After Effects (AE 2025 verified; built-in H.264 15 Mbps output template required, availability on other versions not guaranteed), Python 3, ffmpeg and ffprobe. Render verification and frame extraction additionally require opencv-python-headless (installs numpy)."
---

# AE camera text stops

在 Windows 上用 AE 原生双节点摄像机完成文字演示运镜。**最终 MP4 是成品与验收依据**；
同时保留可编辑 `.aep` 和必要素材，而不只是生成脚本。

## 使用前需提供什么

- 做划词或光标演示时，需要用户自己的原始录屏，能看见实际文字、鼠标或选区变化。
  推荐未二次加速、未人为冻结的原片，保留自然停顿；音轨可选。
- 用户可给 agent 可访问的本地文件绝对路径，或其工具支持的附件。无须上传到 GitHub、
  公开仓库或任何云端；所有媒体分析和处理均在本地完成。
- 用户需说明要聚焦的文字/区域和镜头顺序，可用文字描述或示意图。若未给精确帧号，
  agent 应按真实录屏分析，不要求用户自己提供像素坐标、帧数或全部 JSON 字段，
  不按时长等分猜测。随后从原片一次性生成连续匀速的本地 MP4，`job.media` 指向此准备好的 MP4。
- 本 skill 只提供工具和说明，不附带用户素材，不自动录制、不自动生成划词源片。
  `assets\job.example.json` 只含占位媒体相对路径；单独下载 skill 不会获得视频或直接渲染。
  未提供素材时先请求源文件或可访问的本地路径，不声称已构建或交付。

## 安装与依赖

将整个 `ae-camera-text-stops` 目录复制或链接到当前 agent 支持的技能位置，
保留 `scripts`、`references`、`assets` 和 `tests`；不能只安装 `SKILL.md`。
类别目录仅用于仓库组织，不保证 agent 自动发现。Agent 需支持 Agent Skills（或读取指令），
并获授权执行本地 Python/AE 脚本；不需要 Copilot 专用 API 或运行时。

本工作流面向 Windows/PowerShell，需要 Adobe After Effects、Python 3、`ffmpeg` 和 `ffprobe`。
AE 2025 已验证；构建器必须找到内置 **H.264 15 Mbps** 输出模板，
不保证其他 AE 版本提供该模板。`make_job.py` 和配置测试只用 Python 标准库；
成片检查与抽帧额外需要 `opencv-python-headless`（安装时包含 `numpy` 依赖），
缺失时在任务隔离虚拟环境安装，详见 `references\workflow.md`。

不启动 AE、也不检查真实媒体的配置校验入口：

```powershell
python "<skill-dir>\scripts\make_job.py" "<job.json>" --validate-only
```

它只校验配置结构、坐标、时间线和路径隔离，不证明媒体存在、可解码或成片合格。
构建、渲染及验证命令见下文和 `references\workflow.md`。

## 已确认的设计原则

除非本次用户明确改变要求，采用这些默认值：

- **停的是摄像机，不是视频。** 光标和选字动作正常连续播放；禁止为了延长阅读时间
  插入冻结帧、重复帧片段、静音或局部停顿。原视频本来存在的停留不必删掉。
- 素材放在固定的 3D 平面上，位置/缩放/旋转不打关键帧，完成后锁定。
- 只有摄像机的 **Position 和 Point of Interest** 有动画。目标点确定画面中心看哪组字；
  摄像机相对目标点的位置确定观察角度。位置与目标点同步变动即可同时转动和平移。
- 每个镜头停住读字，再用很短的缓动换位。默认 30fps 下 **4 帧约 0.13 秒**；
  换帧率时按用户要的秒数换算，不能盲目套用 4 帧。
- 三个常用机位：左下、正下、右下，均朝上看。不要把摄像机方位和画面倾斜方向混为一谈；
  用户的新示意图优先于旧版本。
- 视频播放速度和摄像机换位速度分开控制。读字时间不足时降低**整体匀速倍率**，
  例如从 2x 降到 1.25x，再重算换位时机；不冻结选字动作。
- 不默认加入持续推近、滚转、景深、逐帧追踪或结尾回正。它们会让读字机位继续运动。
- 背景默认纯黑；软件渲染、原生效果、无第三方插件。
- **只交付横屏。** 默认仅创建 Landscape 合成、渲染队列和 MP4，不再生成
  Portrait（竖屏）版本；仅当本次用户明确要求竖屏时才添加。
- **成片直接抽帧核对。** MP4 导出后，用本地脚本检查视频并查看抽帧/联系表，
  完成后立即交付。不再为了收尾预览打开剪映、AE 或重新导入成片；不把重开 `.aep`
  作为完成条件。仅当用户明确要求工程检查或编辑时才打开工程。

## 执行顺序

1. **检查并保护素材和工程。** 用 `ffprobe` 查看实际视频轨道尺寸、帧率、帧数、时长、
   音轨；音频尾巴可能比视频长。记录当前 AE 项目。原片不改动，新版本另存；
   修改已有工程前，备份磁盘版本，并另存未保存的 AE 状态。不要丢弃用户未保存的工作。
2. **定位文字与光标时机。** 抽取关键帧，用可见图像或本地 OCR 找目标文字的源图像素坐标；
   中文词和数字口述可能不准确，应按实际区域定位。分析真实选中边界或光标模板，
   不按等分时长猜测换位。只使用本地处理，不上传媒体到第三方。
3. **准备连续素材。** 首选从原片一次性生成目标匀速素材，避免在已经加速过的视频上再次
   编码或误算速度。视频使用 `setpts`，音频使用 `atempo` 保持音调，不使用 loop/freeze。
   步骤及无音轨分支见 `references\workflow.md`。
4. **规划镜头。** 先让摄像机停在第一组字；光标进入中间文字时快速换位并改变目标点；
   光标接近末尾文字时再快速换位。停顿时间可不同，不能牺牲光标同步来强行等分。
   如中间停顿太短，整体放慢视频，而不是插入静帧。
5. **创建 job。** 从 `assets\job.example.json` 复制到本次任务目录，替换路径、源图尺寸、
   帧数、目标坐标、镜头间距与输出尺寸。示例坐标/帧数只适合示例，不可盲目复用。
   三维距离和 zoom 以像素为单位，换分辨率后需按比例调整并检查构图。
6. **运行通用构建器。**

   ```powershell
   python "<skill-dir>\scripts\make_job.py" "<job.json>" --out-dir "<new-work-dir>"
   & "<AfterFX.exe>" -r "<new-work-dir>\build.jsx"
   ```

   `make_job.py` 校验配置，生成固定帧规划、已解析配置和小型 JSX 启动文件；
   不启动 AE、不转码。构建器只在**空 AE 工程**中运行，不覆盖现有项目。
   如 AE 正打开用户的工程，先保存/备份；无法安全切换时先保留当前工程，不强行关闭。
7. **原生渲染。** 软件模式、一次一帧，优先独立 `aerender` 进程。命令必须包含
   `-mfr OFF 1`，不能少第三个参数。Windows 用 `Start-Process -Wait` 等到实际退出。
   不把退出码 0 或文件存在当作成功，检查日志、文件完整性和所有帧。
8. **检查最终 MP4。** 运行通用检查器和抽帧脚本：

   ```powershell
   python "<skill-dir>\scripts\verify_render.py" "<new-work-dir>\job.resolved.json"
   python "<skill-dir>\scripts\extract_frames.py" "<final.mp4>" --job "<new-work-dir>\job.resolved.json" --out-dir "<task-dir>\Review"
   ```

   检查器用 ffprobe/ffmpeg 和本地 OpenCV 检查帧数、解码、黑帧、停顿段透视不漂移、
   指定文字位于画面中心。无纹理/严重压缩素材会导致特征匹配失败，必须报告并改用
   明确的本地人工逐帧检查，不能忽略错误后宣称通过。
   抽帧脚本只读取成片，生成原尺寸 PNG、带帧号/时间的分页联系表和 `frames.json`。
   **必须实际查看联系表**，检查各机位文字、边缘裁切、黑屏和换位前后效果；细节看原尺寸
   PNG。脚本生成图片不等于视觉核对通过。每个成片使用独立的新 Review 目录。
9. **单独核对光标连续性。** 通用检查器不能证明鼠标连续移动。将匀速素材与原片映射帧
   对比，并检查**实际拖选区间**的光标/选中边界。不要把逐字选择的 1–2 帧量化、
   原片开头等待或末尾停留误认为新增冻结。若发现中间新增长时间重复，回到源素材重做。
10. **直接交付，不再打开编辑器。** MP4 的完整解码、自动检查、抽帧观感和光标连续性
    核对完成后立即给出成片路径、时长、速度与修改点。AEP 在构建时保存并由原生渲染器
    使用即可，不再追加工程重开或 GUI 预览流程。保留旧版，不混用废弃版本。

## 文件

- `assets\job.example.json`：三机位、仅横屏输出的参数范例。
- `scripts\make_job.py`：仅标准库；参数校验与安全 JSX 启动文件生成。
- `scripts\build_camera.jsx`：新建 AE 工程，固定视频平面、摄像机位置+目标点动画、渲染队列。
- `scripts\verify_render.py`：通用成片检查；需 `ffmpeg`、`ffprobe`、`opencv-python-headless`。
- `scripts\extract_frames.py`：最终 MP4 抽帧、原尺寸 PNG、分页联系表与时间索引；
  支持 job 机位/换位采样、均匀采样和指定帧；需 `ffprobe`、`opencv-python-headless`。
- `references\workflow.md`：转码/渲染命令、坐标、同步方法、内存/GPU 与 ExtendScript 易错点。
- `tests\test_jobs.py`：配置、路径保护和镜头规划回归测试。
- `tests\test_extract_frames.py`：抽帧规划、真实解码、时间戳、分页和原片/输出保护测试。

## 错误处理与边界

- 不调用未知属性名；摄像机目标点在脚本中是 `ADBE Anchor Point`，不是
  `ADBE Point of Interest`。完整列表和陷阱见参考文档。
- 遇到黑屏，逐项查源素材、图层开关/入出点、无效坐标、活动摄像机和渲染日志；
  不能把整个黑屏归咎于纯黑背景。
- 内存/GPU 失败先切软件渲染、关闭多帧渲染、减少采样。只处理本任务自己的 AE 实例；
  不关闭其他应用、不按进程名批量杀进程、不调整安全设置。
- 优先脚本，不依赖 GUI 手动构建。需要处理窗口/对话框时，仅使用当前 agent 已配置且
  获授权的本地桌面自动化工具；`codex-computer-use` 如可用只是可选示例，不是前置依赖。
  没有 GUI 工具时，请用户手动保存、备份并安全切换到空工程；无法安全切换就保留当前工程，
  不覆盖、不丢弃未保存工作，也不声称构建已完成。
- 不把素材、用户项目或历史对话打包进 skill；只保留通用方法、脚本及非敏感示例。
- 本 skill 是最终“光标连续、摄像机停顿”工作流。以前试过的逐帧跟随、持续滚转、
  中间冻结都不是默认行为。
