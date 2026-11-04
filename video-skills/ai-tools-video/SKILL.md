---
name: ai-tools-video
description: 为用户的抖音「AI工具 · 一天一个超实用的网站」系列生成剪映草稿初版和封面。用户给出新一期素材文件夹(audio.mp3 配音 + 屏幕录制 + *_landscape.mp4 3D运镜)、或只给配音和 GitHub 项目名时使用(仓库截图/项目名 Star 坐标/选字 3D 运镜/README 文档截图可用 tools/capture.mjs 自动抓)：转写配音、看录屏、写 epNN/build.py，生成带用户预设片头/背景/音效/BGM、两帧快速放大镜头、流光框、贴纸、字幕的剪映草稿，并用 封面.pptx 出封面。
---

# AI工具视频：从素材到剪映草稿

用户在剪映专业版 11.5(SVIP)里做竖屏 1080×1920 抖音视频。Claude 负责出**可编辑的剪映草稿初版**和封面，用户在剪映里微调后导出。

## 关键路径

| 东西 | 位置 |
|---|---|
| 工作区(代码、每期产物) | `D:\Desktop\temp\视频流\AI工具\ai-tools-video-workspace` |
| Python 环境 | 工作区 `.venv`（pyJianYingDraft 0.3.0、faster-whisper、python-pptx）。全局 pip 没写权限，一律用 `.venv/Scripts/python` |
| 每期素材 | `D:\Desktop\temp\视频流\AI工具\<NN-名字>\`：`audio.mp3`(已粗剪细剪)、`屏幕录制*.mp4`、`*_landscape.mp4`(开头 3D 运镜，约 4.6s；用户也可能只给一段选字录屏如 `hl.mp4`，用 camera-text-stops skill 自己做——它的脚本要用装了 cv2 的系统 `python`(C:\Python310)，不是 .venv)。**文件夹名可能写错**，以用户说的期数/项目为准 |
| 剪映草稿目录 | `E:\JianYingPro Drafts\` |
| 用户预设(明文!) | `E:\JianYingProData\Presets\Combination\Presets\<名字>\preset_draft\draft_content.json` |
| 音效/音乐缓存 | `E:\JianYingProData\Cache\music\`（哈希文件名） |
| Figma 贴纸 PNG | `D:\Desktop\temp\视频流\AI工具\design\output\`（黄脸_01..09、可爱星星 等） |
| 封面 PPT | `D:\Desktop\temp\视频流\AI工具\封面.pptx`（每期一页：左 3:4、右 4:3） |
| 参考成片 | 工作区 `example.mp4`（第 8 秒的流光框效果）、`AI工具\28-scrapling\28-scrapling.mp4` |

工具代码在工作区 `tools/`：
- `srt_import.py` — 剪映智能字幕导出的 SRT → 同格式 `epNN/transcript.json/.srt`（首选）
- `transcribe.py` — Whisper 逐字时间戳转写 → `epNN/transcript.json/.srt`（兜底）
- `stable_ranges.py` — 找录屏中静止(未滚动)的时间段，用来挑截帧时刻
- `jy.py` — 草稿构建：`Timeline`、`zshot`(两帧快速放大镜头)、`pop`(流光浮起卡片)、`outline`(橙色框)、`sticker`、`text`(关键词高亮字幕)、`phrases`(按标点/词边界切字幕)
- `fx.py` — 生成图形：浮起卡片、流光视频、描边框、渐变大字贴纸 `sticker_wow`、像素对话框 `sticker_tag`
- `preset.py` — **把用户剪映预设注入草稿**：`Preset(名字)`、`Target(草稿目录)`、`embed_combo`、`element`、`explode`、`sound`、`music`
- `opening.py` — 拼片头。**第33期起一律用 `add_opening3`(用户 2026-10-13 重做的预设「片头3」，参考小W)**：「实用工具」居中砸出 → 「第N期」胶囊滑入 → 「今天分享的是」时两行字上移让位、项目卡片转入 + 项目名弹出；参数 `t_shiyong/t_di/t_card/t_end` 都用 `onsets` 卡到音节起点(第33期参考 `ep33/build.py`)。**有入场动画的字要让动画结束时刚好念到**(用户 2026-10-14 第34期反馈)：`t_di` 传「第」的音节起点，函数内部自动提前 `DI_LEAD`=0.333s(「向左滑动」动画时长)，让位关键帧仍和「实用工具」对齐在 t_card；其他带入场动画的弹出字同理，按用户语速提前约一个动画时长。预设里自带的背景复合片段和配音不复制。旧的 `add_opening_short`/`add_opening`(片头2)只留给老期重做
- `jy.zshot(..., src_start=, speed=)` 可以直接用**视频**做两帧快速放大镜头(画面边播边推)，例如作者演示视频；`src_start` 要落在素材一个连续镜头里(先用 ffmpeg `select='gt(scene,0.06)'` 找切点)
- `capture.mjs` — **自动抓 GitHub 素材(2026-10-15 起，不用再等用户截图/录屏)**，见下面流程第 0 步。Node + web-search skill 的 playwright-core + 本机 Chrome 无头 + 本地代理；元数据走已登录的 `gh api`(代理出口 IP 匿名调 API 会 403)。所有图 2 倍分辨率，JSON 里的 box 都是该 PNG 像素坐标，直接喂 `zshot/pop/spot`，不用 Read 图量坐标
- `render.py` — 本地逐帧渲染 MP4(实验性，慢，用户叫停过；默认还是出剪映草稿)
- `preview.py` — 本地粗略合成预览 sheet(不含剪映动画，仅检查构图)

## 流程

0. **自动抓素材**(用户只给项目名/配音时；用户自己给了录屏就用用户的)。每条命令 40~60 秒，输出到 `epNN/cap/`：
   - `node tools/capture.mjs repo <owner/repo> epNN/cap --about "简介的中文翻译(Claude 自己译)"` → `repo_top.png`(2560×1600 仓库首页) + `repo.json`：`stars`(gh 精确数，配音核对用)、`boxes.title`(头像+项目名)、`boxes.star_button`(Star 70.9k 按钮)、`boxes.about`(简介；`--about` 把 About 正文换成中文，开头 emoji 保留——用户 2026-10-15 要求：按钮保持英文，About 正文要中文)、`boxes.about_stars`(侧栏 xx stars)。项目名/Star 流光框：`s = tl.zshot(cap/repo_top.png, …, focus=围绕 box 取小框)`，`tl.pop(s, boxes.title, …)` / `tl.pop(s, boxes.star_button, …)`。**Star 数要和配音念的一致**(用户 2026-10-26 第44期：念 8.3k、页面 8.4k)：页面上的 k 数(`star_text`)和配音不同就加 `--stars 8.3k` 重抓，Star 按钮和侧栏 stars 都在前端改成配音的数再截，坐标不变
   - `node tools/capture.mjs select <owner/repo> epNN/cap/sel --text "README 里一句英文简介的开头" --set "整句中文"`(仓库有中文 README 就用 `--url …/blob/main/docs/README_CN.md --text "中文原句"`，不用 --set) → `select.mp4`(鼠标从下方滑到句首、逐字拖选(起步就有速度、接近匀速、结尾稍减速——用户嫌 ease-in-out 前几个字太慢)、蓝底白字选区、I 形光标，lead 0.5s + dur 2.6s + tail 0.4s) + 自动排好的 `job.json`(≤34 字 2 个停留点，否则 3 个；放大倍数按每段占画面 70% 反推)。然后 `cd epNN/cap/sel && python ~/.claude/skills/camera-text-stops/scripts/render_camera.py job.json` → `landscape.mp4`(1920×1080，约 3.5s)。草稿里 `tl.image("画面", LAND, 0, 时长, 0.95, 540, 900)`(**用户 2026-10-17 第37期：0.67 在剪映里只显示 119%，用户自己放到 168%，即 0.95；两边有字被切掉没关系，要大**)。选哪句：配音钩子说的那句功能简介，第34期是「为 GPT 分配不同的角色，以形成协作实体来完成复杂任务」
   - `node tools/capture.mjs docs <owner/repo> epNN/cap` → `docs.json`：主页 homepage、`docs/` 下的 md(常有 README_CN.md)、子目录
   - `node tools/capture.mjs page <README 或文档 URL> epNN/cap --name readme` → `readme_01.png…`(按段落切开、每张 ≤4800px 高) + `readme.json`：每个 h1-h4/p/li/pre/table/img/video 的 `tile` + `box` + 文字。正片一句一镜：按配音内容在 blocks 里找对应标题/图/表，`zshot(tile, focus=box 附近的小框)`，`spot(…, box, …)` 框重点。**中文 README 优先**(`docs.json` 里有 README_CN 就抓它)
   - README 里的视频(演示视频/视频墙)会列在输出和 `readme.json.videos`(带 MB)。**下载前先问用户**(说文件名、来源、大小)，同意后加 `--download` 重跑这条 page 命令(mp4 是 5 分钟过期的签名链接，只能当场下) → `readme_video_N.mp4`，用 `zshot(..., src_start=)` 当正片镜头。YouTube 链接不下载
   - **量完坐标后别重抓同一页**：README 可能更新、横幅图可能没加载完，重抓的分图切法会变(第35期 cap vs cap3)，build.py 里的坐标就全错了。要补数据就抓到新目录，再按同一段文字对应回来
   - **README 里的 mermaid 流程图截不出来**(懒加载 iframe，截到空白；用户 2026-10-15 说先不修)：需要的话请用户在浏览器里截一张发来(第35期 `ep35/assets/flow_user.png`)，不是每个项目都有。
   - 抓的网页是 en-US 界面；GitHub 自身的按钮文字(Star/Fork/About)保持英文没关系，用户以前的截图也有英文
1. **看素材**：`ffprobe` 各文件时长；录屏按 1fps/0.5fps 拼成 contact sheet 看内容；`stable_ranges.py` 找稳定段；在稳定段里 `jy.extract_frame` 截高清静帧，Read 静帧量出要放大/框选元素的**像素坐标**。
2. **转写**（首选剪映智能字幕，快且不用下模型）：请用户在剪映**新建一个空草稿**（别在要交付的草稿里做，反正保存后会加密）→ 导入 audio.mp3 → 文本 › 智能字幕 › 识别字幕 → 导出 › 勾「字幕导出」选 SRT，存到 `epNN/jianying.srt`。然后 `.venv/Scripts/python tools/srt_import.py epNN/jianying.srt epNN/transcript`：句级时间精确，句内逐字时间按字数均分（实测中位误差 0.17s、90% < 0.45s），关键词弹出时刻偶尔要手动微调 ±0.3s。用户没导出 SRT 时才用 Whisper 兜底：`.venv/Scripts/python tools/transcribe.py <audio.mp3> epNN/transcript medium`（首次会从 hf-mirror 下载模型，CPU 跑 30 秒音频约 5 分钟，放后台）。无论哪种都要检查错字（如「超时用→超实用」「第三时期→第30期」、技术名词），写进 `REPL`。配音里「它」指人时改「TA」。
3. **写 `epNN/build.py`**：复制 `templates/build_template.py`（第30期的成品），改 EP/NAME/DRAFT/路径、每句配音对应的镜头。时间点取自 transcript 的逐字时间；**片头文字时间要吸附到配音真实音节起点**（`onsets.snap(audio, t)` / `onsets.onsets(audio, t0, t1)`；剪映 SRT 句内是均分估的，片头文字必须卡准发音，用户会逐个检查）。短口号版参考 `ep32/build_v2.py`：`OPEN = dict(t_start=钩子结束, lines=[("实用工具", t)], t_di=..., t_card=今天分享的是, t_end=记住这个项目名字)`。全局吸附实测无效，别用在别处。
4. **运行**：`PYTHONIOENCODING=utf-8 .venv/Scripts/python epNN/build.py` → 生成草稿 + `epNN/preview.png`。Read 预览检查构图，迭代。
5. **封面**：**截图要浅色**(用户 2026-10-27 第44期：封面底是黑色，深色截图(暗色模式软件/网站)会和背景混在一起)——优先白底 GitHub README、浅色主题网页；只有深色素材时用浅色 colorScheme 重抓或换浅色底/提亮。**不要用 3D 划词那一帧**(用户 2026-10-16)，用 README 顶部截图(标题+徽章+一句话简介；外链那一行直接从截图里抽掉，白底看不出拼接，参考 `covers/ep35_shot_readme.png`)或其他好看的项目图。裁一张(宽高比 ≈1.657)，跑 `templates/make_covers.ps1 -Vol 0NN -White "..." -Yellow "..." -Shot <png> -OutDir "D:\Desktop\temp\视频流\AI工具\<NN-名字>"`——**封面导出到该期的素材文件夹**(用户要求，和往期 图片1/图片2 放在一起)，不是工作区 epNN。它会先备份 pptx。**别从 bash 直接传中文路径给 powershell**(会乱码，AddPicture 报 ArgumentException)：用 Write 工具写一个带 BOM 的 `epNN/cover.ps1`(内容 `& "…make_covers.ps1" -Vol … -Shot "…" -OutDir "…"`，参考 `ep35/cover.ps1`)，再 `powershell -File` 跑它。
6. 让用户打开剪映检查。**Claude 自己启动剪映会卡住没窗口**（试过多次），别浪费时间，请用户打开。

## 用户的风格要求（务必遵守）

- **背景/片头必须用用户的预设**：背景 = 预设「1分钟背景」整段复合片段(`embed_combo`)；片头 = 预设「片头3」的元素(`opening.add_opening3`)。不要自己重做。
- **镜头关键帧只打两个**：0.2 秒内从 ~78% 快速放大到 100% 后停住（`zshot`）。不要慢慢推、不要多段平移。
- **画面大胆放大**(2026-10-13 两次强调)：**一定要大**——焦点框取得很小，用户自己在剪映里放到 560%(3336 宽的素材焦点约 600px，1920 宽的录屏焦点约 350px)，下拉菜单之类的元素几乎占满画面宽度。**不要求铺满画布**：重点放在画面中间偏上，素材因此往下移、露出背景都没关系(`zshot` 默认 `fill=False`；别为了铺满把重点推到边上)。一句配音一个镜头，换句就切；但画面奇怪/不贴切的镜头宁可删掉，让前后镜头延长——长时间画面不变没关系。
- **所有素材只要入场动画，不要出场动画**(贴纸、框、预设弹出字全部去掉 out 动画，`preset.copy_segment` 和 `jy.sticker/outline` 已默认处理)。
- **重点必须在画面中间偏上、水平居中，绝不贴边**(用户 2026-10-13 第33期发布后反馈：项目名/Star 的流光框太靠屏幕上方)。流光框卡片 `tl.pop` 现在默认从原位置浮起并飞到 `center=(540, 820)`，卡片最宽 980px；橙框 `outline`、贴纸、关键词弹出同理——选 `zshot` 焦点框时让重点落在画布 y≈700~950 的位置。录屏边缘的元素(如页面顶部的项目名、Star)也照样把它放到画面中间，上方露出背景没关系。
- 流光框浮起要**提前**：念到引出重点的词就浮起(如「已经拿下了16K的Star」在「已经」就浮)，不要等数字念出来——否则持续太短看不清。
- **项目名、Star 等重点**用 example 第 8 秒的效果：背景压暗 + 白卡片回弹浮起 + 粉色流光环绕（`tl.pop`）。
- 列表/表格里的重点逐个框出，配「提示音」。用户 2026-10-14 嫌橙色细框 `tl.outline` 太简单，参考小W 要**聚焦框** `tl.spot(shot, box, start, end, 截图, out_png)`：背景压暗 + 框住的元素原地做成白底圆角卡片稍微放大(1.15，回弹) + 外圈红色粗虚线圆角框。`start` 放在镜头放大结束后(镜头开始 +0.25s)。**用户 2026-10-15 确认「效果非常棒」，以后一律用 spot，不再用 outline**。同一镜头多个框时前一个在下一个出现时结束(别叠压暗)，参考 `ep35/build.py` 的 `spots()`；框离焦点框边缘要留余量(卡片放大 1.15 会被画面切掉)，两个重点相距太远就按配音拆成两个镜头。
- **画面要有设计感，视觉重心偏上**：贴纸/标签放在画面上半部(约 y 300~650，压在内容上沿)，不要放在下面挨着字幕；结尾大贴纸放画面正中(y≈900)，挡住内容也没关系。
- 贴纸要**大**（`STICKER_SCALE=1.45` 已默认放大）：渐变大字+黄脸 `sticker_wow`（复刻TA、应有尽有、非常好用），对话框标签 `sticker_tag`（生气了、撒娇、免费·无限制）。
- **弹出字不能超出画面**(用户 2026-10-17 第37期「Claude Code」用「弹上来（砰）」左右被切掉)：`T.explode(..., text=)` 现在会用预设字体估算宽度(`preset.fit_text`，标定 1em≈6.1px×字号×缩放)，超过画布 90% 宽自动缩小片段并打印提示；英文/长词优先换短文字或字体窄的预设(「直接出现（叮/嘟噜）」用 AaHouDiHei，比 UnboundedSans 窄)。
- 用户 2026-10-17 重做了「直接出现（嘟噜）」「直接出现（叮）」(现在是复合片段：文字 + 「嘟咚，提示音1」/「提示音」)，还新建了「黄色弹上来（砰）」「紫色弹上来（砰）」「花字1」「片头滚筒」，`Preset` 会自动拆开复合片段。
- 关键词弹出优先用用户预设：「弹上来（砰）」「文字砸下来（砰）」「直接出现（叮）」「直接出现（嘟噜）」「向右滑入（嘟噜）」，`T.explode(Preset(名), t, text=..., until=下一段开始)` 只换文字；**必须传 `until`**，否则会拖进下一段（第31期「Token消耗」压到了片头「一天一个」）。「逐字强调花字」用户嫌丑已删除——要强调的词用 Figma 风格的 `sticker_wow`（渐变大字+黄脸），用户更喜欢。其他可用预设：圈出来（叮铃）、框出来、箭头（叮叮叮）、短划线/长划线、好棒呀(wow)、太方便了吧。
- 字幕：抖音美好体、白字黑描边、关键词黄色高亮，单独一条轨道。用户有 SVIP 也可能删掉改用剪映智能字幕。片头大字期间、结尾大贴纸期间不放字幕。长句由 `jy.phrases` 按 jieba 分词边界切（不会把「减少」切成「减/少」）。
- BGM(用户 2026-10-16：别总用 Mane，轮着用)：`BGM = variety.bgm(EP)`，工作区 `BGM候选/` 里 4 首(Mane、Manten Diloty、Montagen bandido、The invincible king 2)按期数轮换，本地文件直接放(空 id 剪映能播)。音量约 0.18。
- **只用用户收藏的音效**(用户 2026-10-16 给了剪映「收藏」截图，23 个，抄在 `variety.FAVORITES`；剪映不在本地存收藏列表，读不到，收藏变了请用户再截图)。8 个科幻/科技类收藏(科幻按钮音、科技点击系统音、科幻点击叮的音效素材、游戏点击 音效、激活出现提示、科技电波音、叮咚（紧张）、亮一下)本地没有缓存也不在预设里，`Cycle` 会先跳过并打印；用户把它们放进一个组合预设(或在音效面板试听)后自动可用。
- **两个音效别挨太近**(用户 2026-10-26 第44期：「直接出现（嘟噜）」自带嘟咚，0.2s 后又一个聚焦框提示音，听着重叠)：弹出字预设自带音效时，同一时刻附近(±0.4s)的聚焦框用 `spots(..., sfx=False)` 不再加提示音。
- **音效要轮换**(用户 2026-10-16：一直用「提示音」太同质化)：`tools/variety.py` 按用途分组 `CUE`(聚焦框提示音 10 个)、`HIT`(标签贴纸砸下)、`WOW`(渐变大字贴纸)、`POP`(项目名/Star 流光框)，`sfx_cue = V.Cycle(V.CUE, EP)` 每次 `sfx_cue()` 取下一个，参考 `ep35/build.py`。新加音效名必须在 `preset.cache_index()` 里(或预设里有)，加完用 `tools/test_sfx.py claude-音效测试-xxx "新音效"` 生成测试草稿验证(别传成品草稿名)。**黑名单**(用户 2026-10-16 嫌难听，永远不用)：收银机的叮(「叮，收银机提示音1」)、闪亮登场音效、哐，撞击轻响、滴，提示音、哇哦不错哟，女声、轻快的嗖(素材里连响 3 声，用户 2026-10-16 第36期)——在 `variety.BLACKLIST`，Cycle 会自动跳过。**音效开头有静音的要提前放**：`T.sound(op, name, V.sfx_time(name, t), …)`(「叮」前 20 帧、「提示音」前 9 帧是空的，用户实测；其他从缓存文件自动量)。片头 `add_opening3` 里「第N期」的提示音是故意带静音对齐的，别动。
- **易限流内容要局部模糊**(用户 2026-10-16)：画面里出现的网址/链接/邮箱、注册登录付费充值、赞助商广告和横幅、GitHub 顶栏 Sign in/Sign up/Pricing，都要糊掉。做法：`capture.mjs` 的 repo/page 输出里有 `risky`(含整个「赞助/Sponsor/广告」章节)，build.py 里所有截图先过 `fx.blur_risky(png, json, a("safe_xxx.png"))` 再用(等同剪映模糊特效+蒙版，镜头怎么推都跟得住)。用之前 Read 一下 safe 图确认没漏；视频素材(作者演示视频等)有广告的话在剪映里加模糊特效+蒙版，或告诉用户。
- **聚焦框至少停留约 0.8s**(第35期「遗忘」框只有 0.43s，用户嫌太短)：时间短的句子就提前出框，开始时间不早于镜头开始 +0.25s。
- **每期再给 5 个 #话题**(用户 2026-10-16)：如 `#GitHub #网文小说 …`，一个平台/来源 + 受众/题材 + 功能/技术词，和标题一起写进 `epNN/title.txt` 交付时告诉用户。
- **每期给一个标题**(用户 2026-10-16)：格式 `第N集 | 一句有情绪的话!`，如「第35集 | 网文小说作者有福了!」——点出受众/痛点，写进 `epNN/title.txt` 并在交付时告诉用户。
- **标题总长 ≤20**(用户 2026-10-24，第44期起)：整行(含「第N集 | 」)按 汉字/全角标点=1、英文/数字/空格/半角符号=0.5 计，前缀「第NN集 | 」占 4.5，后面 ≤15.5。写完用 `python -c "import sys;print(sum(0.5 if ord(c)<128 else 1 for c in sys.argv[1]))" "标题"` 核对。
- 用户说过「我相信你的审美」，细节可自行发挥，但以上几条是明确反馈过的。

## 片头音效（用户 2026-10-07 校正，`opening.add_opening` 已实现）

- 打字声：前 12 帧(30fps)是静音 → 截掉(`src_start=12/30`)，和文字同时出；第 34 帧后太长 → 截掉。
- 提示音：前 8 帧静音，但「第N期」有入场动画，所以带着静音和文字开头对齐刚好。
- `T.sound(..., src_start=, max_dur=)` 可截任意音效的头尾。

## 剪映草稿的坑（已踩过）

- **绝不覆盖用户可能在改的草稿**：`Timeline.save` 现在会检查同名草稿，有 `.backup` 或已加密就拒绝(2026-10-13 第33期 v2 被我重建覆盖过一次)。改 build.py 的脚本出错时别让后面的构建命令照样跑(用 `&&`)。
- **剪映保存过的草稿会被加密**，Claude 读不回来。所以每次生成**新名字**的草稿（`-v2`、`-v3`），不要覆盖用户正在编辑的版本。`allow_replace=True` 只对 Claude 自己的新名字用。
- **音效/音乐靠 `effect_id`/`resource_id` 识别，不是 path**。只改 path 会全部变成模板那个音效（第29期 v2 全成了「砰」）。`preset.sound()` 先从预设里复制同名音效素材；预设里没有的，用 `preset.cache_index()` 查：它读剪映素材面板的接口缓存 `E:\JianYingProData\Cache\ressdk_db\*\rp.db` 的 `http_cache` 表，得到 名字 → effect_id + md5，**缓存文件名 = md5**（文件内容 md5 也等于它，已验证）。凡是用户在剪映里试听/用过的音效都可用（2026-10-06 约 121 个，用户已在 `claude-音效测试-v2` 里试听确认全部对得上；`list(preset.cache_index())` 看全部）。名字必须是剪映里的完整标题（如「哐，撞击轻响」「叮铃～魔法音效」）。没试听过的音效没缓存 → 请用户在剪映音效面板里点一下试听即可，不用再做预设。验证音效：`tools/test_sfx.py claude-音效测试-xxx "音效1|音效2"`——**它会新建/覆盖同名草稿**(每 2 秒一个音效+音效名字幕)，**绝不能传成品草稿名**(2026-10-16 把第36期成品覆盖成了音效测试，脚本现在会拒绝已存在的非测试草稿)。
- 预设 JSON 里的 `##_presetpath_placeholder_..._##` 要替换成 `E:/JianYingProData/Presets/Combination`（`Preset` 已处理）。嵌套复合片段全部平铺在外层 `materials.drafts`，复制片段时要连同引用的所有层级一起带上（`_copy_draft_entry` 已处理）。
- pyJianYingDraft 生成的明文草稿在 11.5 能正常打开编辑（已验证）。片段素材时长不足会报 `截取的素材时间范围超出`——生成素材时多留 0.2s。
- 草稿引用的 PNG/MP4 都在工作区 `epNN/assets/`，不要删。
- 封面 PPT 里文本框居中≠文字居中：`make_covers.ps1` 已把底部文字设为段落居中并把文本框移到封面中心。Vol 标签要关掉 WordWrap 否则 `Vol.029` 会折行。
- 封面导出（2026-10-07 修）：以前把形状复制粘贴到新演示文稿再导出，新文档主题字体不同，**英文/数字会从微软雅黑粗体变成细字**（第31期「Token」「90%」）。现在是另存临时副本→放大页面→手动平移全部形状（PowerPoint 放大页面时不移动 Top 为负的形状）→整页导出→按封面矩形裁剪。导出后 Read 图片1/图片2 检查英文是否粗体、顶部「一天一个」和 Vol 是否在。

## 前 9 秒（用户 2026-10-12 根据第30/32期跳出曲线定）

- 第30/32期每秒跳出率：0~1s 和同类持平甚至更好；**钩子后半段(2~4.5s)和口号刚出现那一下(约5s)是同类的 1.5~2.4 倍**；10s 以后和同类持平。
- 所以：钩子第一句用 3D 运镜，**第二句必须换新镜头**(新信息+贴纸)；钩子画面一直接到片头卡片出现，**中间不能有空帧/纯背景**；口号改成「实用工具第N期」(约1.2s)，口号期间项目卡片常驻画面。
- 旧配音里还有「一天一个」的，可以像 `ep32/build_v2.py` 一样把那一段从 audio 里剪掉(ffmpeg atrim+concat，之后所有时间用 `S(t)` 前移)。

## 时间参考

钩子 0~约4.5s（3D 运镜 + 关键词弹出 → 第二句换镜头）→ 「实用工具第N期」片头(卡片常驻) → 「今天分享的是」项目名 → 「记住这个项目名字」流光框 → 正片一句一镜 → 结尾大贴纸。总长目标 25~28s(语速约 5.5 字/秒)。文案用 `ai-tools-script` skill 改写。
