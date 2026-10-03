# 实操与故障排查

## 准备媒体：不要把摄像机停顿做成视频冻结

读取视频轨道，而不是只读容器总时长：

```powershell
ffprobe -v error -show_entries stream=codec_type,width,height,r_frame_rate,duration,nb_frames,pix_fmt:format=duration -of json ".\input.mp4"
```

举例：原画面 186 帧、30fps，即 6.2 秒；1.25x 后是 4.96 秒，
在 30fps 时间线上向上取整为 149 帧，合成长度约 4.966667 秒。
小于一帧的末尾取整不是在拖选过程中插入停顿。始终检查新素材实际帧数。

有音轨时：

```powershell
ffmpeg -hide_banner -loglevel error -n -i ".\input.mp4" `
  -filter_complex "[0:v]setpts=PTS/1.25,fps=30[v];[0:a]atempo=1.25,atrim=duration=4.966666667[a]" `
  -map "[v]" -map "[a]" -t 4.966666667 `
  -c:v libx264 -crf 16 -preset medium -pix_fmt yuv420p `
  -c:a aac -b:a 192k -movflags +faststart ".\Assets\continuous.mp4"
```

无音轨时，不引用 `[0:a]`：

```powershell
ffmpeg -hide_banner -loglevel error -n -i ".\input.mp4" `
  -vf "setpts=PTS/1.25,fps=30" -an -t 4.966666667 `
  -c:v libx264 -crf 16 -preset medium -pix_fmt yuv420p `
  -movflags +faststart ".\Assets\continuous.mp4"
```

命令中的速度、fps、时长必须根据当前任务重算。速度很大/很小时，使用多个
`atempo` 串联，使每级倍率处于 0.5–2 范围内。用 `-n` 防止意外覆盖。
不能通过 `loop`、`tpad`、冻结图层或跳跃时间重映射来延长中间读字段。

## 坐标和时间规划

- `target` 是**原素材像素坐标**，不是合成坐标，也不是屏幕截图缩放后的坐标。
  OCR 若使用裁剪/放大图，先还原到原视频像素。
- 对于居中固定的视频平面：`worldTargetX = compWidth/2 + sourceX - sourceWidth/2`，
  Y 同理。Z 为零。`cameraPosition = worldTarget + cameraOffset`。
- AE 的 Y 向下为正。要从下往上看，offset Y **为正**；从上往下看则为负。
  左右机位分别用负/正 X offset。视频前方的摄像机通常用负 Z。
- 摄像机“位置”和“目标点”同时增加相同位移，观看角度保持不变而取景平移。
  改变相对位移改变透视。手动旋转通道保持零，双节点自动朝向产生真实透视。
- 放慢/加速源视频后，光标到达目标的时间也随之改变。按原片帧号除以倍率映射到
  输出时间，再在目标附近安排短切换；不能沿用上个速度的关键帧时刻。
- 机位停留由两枚相同值的关键帧构成。停留段用 HOLD；两个不同机位之间才用 BEZIER。
  Position 和 Point of Interest 必须用相同时间点和缓动参数。
- 文字在摄像机目标点上应投影到画面中心。默认仅横屏输出，不创建 Portrait
  合成、渲染队列或文件。不要只验证整张图片可见，要检查当前文字组没有被裁掉。
- 不为了保持一样的停顿长度而打断光标动作；镜头停留长度不等是正常的。

## 构建

在当前任务目录复制/编辑 `job.example.json`，不要改 skill 里的示例，也不要在 skill
目录存放用户素材或导出。路径相对于 job.json 所在目录。

```powershell
python "<skill-dir>\scripts\make_job.py" ".\job.json" --validate-only
python "<skill-dir>\scripts\make_job.py" ".\job.json" --out-dir ".\ae-job"
& "<AfterFX.exe>" -r "<absolute-path>\ae-job\build.jsx"
```

JSON 被 Python 解析、校验并安全序列化为 JSX 对象；不要对从网页/文件读取的任意文本
直接使用 ExtendScript `eval`。启动文件再调用安装目录中的通用 JSX。
构建器保留现有项目和文件，遇到非空工程/已存在输出会报错，不能移除这些保护。

AE 接受 `-r` 后不代表脚本已完成；等 `build-report.txt` 中出现 SUCCESS 或 ERROR。
成功消息仅表示工程已保存，**不表示成片已渲染**。
若只为离线构建启动了一个新的 AE 实例，可以在启动脚本里设置
`app.exitAfterLaunchAndEval = true` 来释放内存；不要对用户已有工作实例盲目退出。

## 渲染

优先独立渲染进程，避免 GUI 预览和渲染器同时占满内存：

```powershell
$args = '-project "C:\work\output\camera.aep" -mem_usage 10 70 -mfr OFF 1 -log "C:\work\ae-job\render.log"'
$render = Start-Process -FilePath "<aerender.exe>" -ArgumentList $args -NoNewWindow -Wait -PassThru
Get-Content "C:\work\ae-job\render.log" -Tail 20
```

重要：

- `-mfr OFF 1` 是一个三参数组，不能写成 `-mfr OFF`，否则后面参数会被误解析。
- 某些 AE 导出错误仍以退出码 0 返回。查找 ERROR/WARNING、内存或 GPU 警告，
  再用 `ffprobe` 和完整帧解码确认。零字节 AAC/M4V 临时文件不是成片。
- `-reuse` 在某些状态下会立即返回，甚至没有真正产生输出。不要连续重复点击渲染；
  先确认渲染队列和进程状态，再换独立渲染器。
- 软件模式是 `app.project.gpuAccelType = GpuAccelType.SOFTWARE`。
  多帧渲染关闭；运动模糊采样可用 8/16。无需景深、投影或其他 GPU 效果。
- RenderQueueItem 状态为 DONE 时，可能不能修改其 `render` 或 `OutputModule.file`。
  新版本用新的队列项；不要试图直接重用 DONE 项目。
- GUI 中二分之一预览不能影响最终导出；渲染队列明确设置 `Resolution = Full`。

## 黑屏与脚本陷阱

按顺序检查：

1. 素材文件是否存在、所有源帧是否可解码；图层开关、in/outPoint、合成时长是否正确。
2. 是否有错误的 timeRemap、stretch、父级、solo 或已结束的预合成。
3. 当前是否为活动摄像机视图；摄像机/目标点的每一轴是否是有限数。
4. `app.disableRendering`、GPU 警告和内存分配失败。不要把缺帧当作纯黑背景正常结果。
5. 在输出电影中检查每一帧，不只检查开头；GPU 失败曾造成前面正常、后半段全黑。

已验证的 AE 2025 match names：

```javascript
camera.property("ADBE Transform Group").property("ADBE Position");
camera.property("ADBE Transform Group").property("ADBE Anchor Point"); // Point of Interest
camera.property("ADBE Camera Options Group").property("ADBE Camera Zoom");
camera.property("ADBE Camera Options Group").property("ADBE Camera Depth of Field");
video.property("ADBE Material Options Group").property("ADBE Accepts Lights");
```

`ADBE Point of Interest` 不是这里正确的 match name，会返回 null。
先设置图层 comment、素材、时间范围，再锁定图层；锁定后设置 comment 也可能失败。
Position 分离成 X/Y/Z 可避免不必要的空间曲线。向量目标点使用手动零空间切线、
关闭空间自动贝塞尔，并验证所有关键帧与中间值没有 NaN。

## 验证与依赖

`make_job.py` 和配置测试只用 Python 标准库。
`verify_render.py` 使用 OpenCV。先尝试运行；若提示缺少 cv2，再在任务隔离虚拟环境安装
`opencv-python-headless`，不要给用户全局 Python 环境随意加依赖。

通用检查器对停顿中间的帧做特征匹配和单应性测量，目标应居中，角点漂移通常低于
1 像素（编码误差）。快速换位帧有运动模糊，特征不足并不证明运动错误；用原生关键帧
时长/插值、停止前后画面和可见的中间转移帧验证这些过渡，不用模糊帧冒充读字质量。

连续光标须另验：

- 对照原片：输出第 n 帧附近应来自原片对应的匀速时刻，允许帧率转换的单帧取整。
- 拖选时可测选区的**连续连通区域右边界**。只取一个大 ROI 的所有蓝色像素最大 X
  会把未选文字/超链接混入，得出错误的恒定位置。
- 箭头鼠标、文本 I 形光标、拖选边界需区分；模板匹配需检查置信度。
- 1 像素选区边缘误差、按字符选择造成的 1–2 帧重复是编码/量化现象。
  不能用放宽阈值掩盖新增的数百毫秒冻结。
- 不修改原片已有停顿，除非用户提出删掉。

完成后重开工程核对链接、摄像机位置+目标点关键帧与输出一致，再提供文件位置。
