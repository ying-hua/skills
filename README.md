# Agent Skills

按类别分享的 [Agent Skills](https://agentskills.io/specification)，包含指令、脚本和参考文档，
不依赖 Copilot 专用 API 或运行时。

## 视频技能

| Skill | 简介 |
| --- | --- |
| [ae-camera-text-stops](video-skills/ae-camera-text-stops/SKILL.md) | 用 After Effects 原生摄像机制作可编辑的文字演示运镜：停住读字、快速换位，视频和光标连续播放，默认仅横屏。 |
| [science-video-kit](video-skills/science-video-kit/SKILL.md) | 用纯 Python 程序化制作几分钟长、画面惊艳的中文科普短视频：2D/GPU 画面、合成音效与配乐（或用你的 BGM）、响度标准化压制；共享基础设施，但用风格目录和本地风格日志保证每个视频风格都不同。 |

## 使用前需提供什么

使用 `ae-camera-text-stops` 做划词或光标演示时，需提供**自己的原始录屏**，能看见实际文字、
鼠标或选区变化。推荐未二次加速、未人为冻结的原片，保留自然停顿；音轨可选。
可给 agent 可访问的本地文件绝对路径，或其工具支持的附件；无须上传到 GitHub、
公开仓库或任何云端，所有媒体分析和处理均在本地完成。

还需说明要聚焦的文字或区域，以及镜头顺序，可用文字描述或示意图。
不必自己填写像素坐标、精确帧号或全部 JSON 字段；agent 应根据真实录屏分析文字、光标和选区时机，
不能按时长等分猜测，再从原片一次性生成连续匀速的本地 MP4，供 `job.media` 使用。

Skill 是工具和说明，**不附带用户素材，不自动录制，也不自动生成划词源片**。
`assets\job.example.json` 只有占位媒体相对路径；单独下载 skill 不会获得视频或直接渲染。
未提供素材时，agent 应先请求源文件或可访问的本地路径，不能声称已构建或交付。
不要把真实录屏、用户 AEP 工程或导出文件放进本仓库。

## 安装与运行环境

类别目录只是仓库组织方式，不保证各 agent 自动发现。安装时，将**整个**
`ae-camera-text-stops` 目录复制或链接到所用 agent 支持的技能位置，不能只复制 `SKILL.md`。
下面是 Windows PowerShell 示例，请将 `<agent-skill-root>` 替换为该 agent 的实际技能根目录；
若目标已存在，先自行检查和备份，不覆盖已有安装。

```powershell
git clone https://github.com/ying-hua/skills.git
$skillRoot = "<agent-skill-root>"
$destination = Join-Path $skillRoot "ae-camera-text-stops"
if (Test-Path -LiteralPath $destination) {
    throw "Skill destination already exists; inspect and back it up before installing."
}
New-Item -ItemType Directory -Path $skillRoot -Force | Out-Null
Copy-Item -LiteralPath ".\skills\video-skills\ae-camera-text-stops" -Destination $destination -Recurse
```

**格式通用不等于运行环境通用。** Agent 需支持 Agent Skills（或能读取这些指令），
并获授权执行本地 Python 和 AE 脚本。本技能的工作流面向 Windows/PowerShell，
需要 Adobe After Effects（AE 2025 已验证）、Python 3、`ffmpeg` 和 `ffprobe`。
构建器依赖 AE 内置 H.264 15 Mbps 输出模板，不保证其他 AE 版本提供该模板；
成片检查额外需要 `opencv-python-headless`（安装时包含 `numpy` 依赖）。
具体命令、工程保护和检查边界见 [SKILL.md](video-skills/ae-camera-text-stops/SKILL.md)
及 [workflow.md](video-skills/ae-camera-text-stops/references/workflow.md)。

## science-video-kit

**使用前需提供什么**：一句话主题即可。可选：BGM 文件的本地路径（不提供则由 agent 合成配乐）、
目标时长、横屏或竖屏、目标文件大小。所有画面和声音都在本地由代码生成，skill 不附带任何素材。
agent 会在你的视频工作区维护一份本地 `STYLE_LOG.md` 来记录已交付视频的风格，避免下次雷同；
这份日志、渲染结果和 BGM 都留在本地，不要放进本仓库。

**运行环境**：Python 3.9+，需安装 `numpy`、`scipy`、`pycairo`、`opencv-python`、`Pillow`，
以及 PATH 中的 `ffmpeg` / `ffprobe`。GPU 画面另需 `moderngl` 和支持 OpenGL 4.3 的显卡。
字体默认使用 Windows 自带的 Noto Serif/Sans SC 和 Georgia，在 Linux/macOS 上会回退到 `fc-match`
或常见中文字体，也可在项目中用 `vk_core.set_fonts` 指定。安装方式同上：复制**整个**
`science-video-kit` 目录到 agent 的技能根目录。自测：

```bash
pip install numpy scipy pycairo opencv-python Pillow moderngl
python video-skills/science-video-kit/tests/test_kit.py
```

