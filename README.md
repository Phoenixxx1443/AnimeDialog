# AnimeDialog · 台词提取、字幕生成与人物审核

将动漫或电视剧视频中的台词和字幕整理成按人物分类的双语台词本，在同一窗口播放、审核、编辑并导出字幕与文档。

Local dialogue transcription and subtitle editing for anime and TV series, with speaker diarization, bilingual translation, and SRT export.

**当前版本：1.1.4 · Windows 11 x64 · Python 3.12+ · MIT**

AnimeDialog 默认在本机处理。首次使用可下载模型，也可导入已有模型；模型准备好后，识别、翻译和人物建议均可离线运行。翻译也可手动填写，或自行配置大模型 API。

适合制作人物台词本、提取视频字幕、生成双语 SRT、核对对白和翻译字幕。

## 功能

- **导入多集视频：** 支持 MP4、MKV、MOV 等格式，同一作品的多集共享人物、别名和声音样本。
- **生成双语台词：** 识别原声及时间轴，优先利用内嵌或附加字幕；可调整字幕区域后提取烧录字幕。默认生成原文与简体中文对照，中文原声保留一份原文。
- **无字幕翻译：** 手动输入译文，或使用本地 Qwen3、Chat Completions 兼容 API，翻译选句或批量补充空白译文。已有译文进入建议比较，保留人工修改。
- **提出人物归属建议：** 结合声音特征、称呼和上下文提出姓名与归属候选，保留依据；证据不足时使用临时人物名，等待人工确认。
- **对照视频审核：** 点击台词定位视频，搜索、筛选、循环本句，编辑原文、译文、人物、时间和备注；支持新增、删除、拆分、合并及批量归类。
- **保存人工修改：** 人物确认与文字校对分别记录，支持自动保存、撤销和重做；重新识别及 HTML 回导结果进入建议比较，人工修改不会自动被覆盖。
- **按台词剪辑视频：** 独立片段导出页，选择一句或多句台词，调整片段时间和顺序，分段导出或合并为 MP4；支持跨集选句和暂停继续。
- **导出台词本：** 支持 Word、离线 HTML、TXT、SRT 和 JSON。HTML 可选择本地视频进行人工归类，保存后重新导入软件。
- **管理任务与模型：** 队列支持暂停、继续、取消和重试；已完成阶段保存检查点，模型支持本地导入、下载恢复及完整性校验。

播放器支持 **0.5×、0.75×、1×、1.25×、1.5×、2×、3×、5×**，以及 **原始比例、16:9、4:3、1:1、21:9、铺满**。退出软件后保存倍速、画幅、音量和布局。

## 安装

Windows 安装包包含 Python、Qt、播放器及处理引擎，使用者无需另装 Python。大型模型单独下载或导入。

从 [Releases](https://github.com/Phoenixxx1443/AnimeDialog/releases/latest) 下载：

- **[Windows 安装包](https://github.com/Phoenixxx1443/AnimeDialog/releases/download/v1.1.4/AnimeDialog-1.1.4-Windows-x64-Setup.exe)**：下载后运行即可安装。
- **[源码压缩包](https://github.com/Phoenixxx1443/AnimeDialog/releases/download/v1.1.4/AnimeDialog-1.1.4-Source.zip)**：解压后可从源码运行或自行打包。

升级前关闭 AnimeDialog，安装到原目录；项目与已下载模型可以继续使用。大型附件通过 Releases 提供，不作为 Git 文件提交。

需要从源码运行或自行打包时，按下文操作。

## 用法

### 1. 创建作品并添加视频

点击“新建作品”，填写作品名并选择保存位置。点击“添加视频”，可一次添加多集。在左侧剧集的“设置”菜单中调整集数顺序、选择原声语言和音轨，并添加 SRT、ASS 等字幕。

视频有烧录字幕时，在“语言、音轨与字幕”中启用画面字幕提取，用“查看字幕区域”调整范围。

### 2. 准备模型并开始处理

打开“模型与工具”，下载或导入所需模型：

| 用途 | 模型或引擎 |
| --- | --- |
| 原声识别 | Whisper.cpp / large-v3-turbo |
| 选句精细重识别 | Whisper.cpp / large-v3 |
| 声音切分与声音特征 | sherpa-onnx 对应模型 |
| 烧录字幕提取 | RapidOCR |
| 本地翻译、姓名及上下文候选 | llama.cpp / Qwen3-8B-GGUF Q4_K_M |

选择单集后点击“开始处理”；选择“全部剧集”可按队列处理全部集。界面显示当前阶段、进度与失败原因。默认尝试显卡运行，原生推理引擎失败时回退到 CPU。

### 3. 播放、审核和修改

左侧选择剧集或人物，右侧搜索或筛选台词。点击台词即可定位视频；播放器下方可以调整倍速、画幅和循环播放。

在编辑区修改文字、时间及人物。多选台词后使用“批量归类”加入现有人物或新人物。明确的单人片段经人工确认后，可设为人物声音样本，再为其他台词生成匹配建议。

“人物已确认”和“文字已校对”分别保存。自动识别、声音匹配和姓名推测都是候选，人工核对后才视为审核完成。

没有字幕时，先完成原声识别，再用以下方式填写译文：

- **手动翻译：** 选中台词，点击“手动翻译”或按 **Ctrl+3**，在中文框输入；自动保存并标记为人工翻译。
- **大模型翻译：** 点击“翻译原文”或按 **Ctrl+T**，选择选中台词、当前集补译或整个作品补译。可使用本地 Qwen3，或填写兼容 API 的地址、模型 ID 和 API Key。地址支持 Base URL（如 `https://你的服务/v1`）及完整 `/chat/completions` 地址；本机服务允许 HTTP。

使用 API 而未安装 Qwen3 时，在“语言、音轨与字幕”取消“本地生成中文翻译和人物姓名候选”，识别完成后单独翻译。API 模式只发送原文和上下文，视频与音频不上传；密钥由当前 Windows 账号加密保存，不写入作品或导出文件。接口协议可参考 [Chat Completions 文档](https://api-docs.deepseek.com/api/create-chat-completion/)。

空白译文直接补齐并等待文字校对；已有译文及处理期间修改的台词进入“识别、翻译与回导建议”。可用 Ctrl / Shift 多选建议后接受或忽略。翻译任务支持暂停、继续和重试，译文生成不会确认人物。

### 4. 导出或回导

点击“导出台词本”，选择格式、范围及时间顺序或人物分组。SRT 按剧集分别导出，可选原文、中文或双语。

导出的 HTML 可离线打开，选择本地对应视频后进行复核、编辑及人物归类。网页中点击“保存 HTML 副本”，再在软件中使用“文件 → 导入旧台词 / HTML”回导；有修改冲突时先比较，再决定是否接受。

详细说明见 [中文使用说明](使用说明.html)，下载后可用浏览器打开。

### 5. 按台词裁剪视频

在“台词审核”中用 Ctrl / Shift 选中一句或多句台词，点击列表下方“片段”或按 **Ctrl+Shift+K**，加入独立的“片段导出”页；右键菜单也提供入口。可返回选句继续添加其他剧集的台词，同一句可以重复添加。

拖动片段或使用上移、下移调整顺序。双击片段或点击“预览”定位播放，到片段结尾暂停；F6 可循环。“调整时间”只改变片段的开始与结束，不修改台词时间。片段列表自动保存在作品项目中。

**分段导出**在选择的位置新建子目录，按列表顺序编号保存 MP4；**按顺序合并导出**生成一个 MP4。使用原视频与剧集所选音轨，正常速度输出，保持画面比例；合并时统一首段的画幅、帧率，其他片段留边适配，无声片段保留静音。边界以视频帧精度裁剪，建议先预览核对。输出画质可选最高 1080p、720p 或原分辨率。

导出进入现有任务队列，可暂停、继续和重试，已完成片段可以复用。原视频不修改，已有文件不会被覆盖；查看完成路径可点击“打开导出目录”。

## 常用快捷键

按 **F1** 查看完整快捷键清单。

| 操作 | 快捷键 |
| --- | --- |
| 播放 / 暂停 | F5；列表或视频中也可按空格 |
| 循环本句 | F6 |
| 确认人物 / 校对文字 / 下一条待核 | F7 / F8 / F9 |
| 校对文字并下一句 | Ctrl+Enter |
| 上一句 / 下一句 | Alt+↑ / Alt+↓ |
| 后退 / 前进 2 秒 | Alt+← / Alt+→ |
| 搜索 / 保存 | Ctrl+F / Ctrl+S |
| 手动翻译 / 大模型翻译 | Ctrl+3 / Ctrl+T |
| 加入片段 / 打开片段页 | Ctrl+Shift+K / Ctrl+5 |
| 返回选句 | Ctrl+1 |
| 片段上移 / 下移 / 移除 / 预览 | 片段列表中 Ctrl+↑ / Ctrl+↓ / Delete / 空格 |
| 批量归类 | Ctrl+Shift+B |
| 撤销 / 重做项目操作 | Ctrl+Alt+Z / Ctrl+Alt+Y |
| 恢复默认布局 | Ctrl+0 |

文字输入框中的空格、Delete、Ctrl+Z 和 Ctrl+Y 保持正常文字编辑行为。

## 从源码运行

在 Windows 11 上安装 Python 3.12 或更新版本，克隆仓库后运行：

```powershell
git clone https://github.com/Phoenixxx1443/AnimeDialog.git
cd AnimeDialog
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.venv\Scripts\python.exe scripts\bootstrap_tools.py
.venv\Scripts\python.exe main.py
```

`requirements-lock.txt` 记录 Windows 构建依赖；`bootstrap_tools.py` 从发布者下载 FFmpeg、FFprobe、Whisper.cpp 和 llama.cpp 到 `vendor/`。应用启动后，在“模型与工具”中另行准备模型。

如需使用已有项目，也可指定项目文件夹：

```powershell
.venv\Scripts\python.exe main.py --project "D:\AnimeDialog作品\我的作品"
```

获取脚本在发布者没有提供 Whisper Vulkan 包时会取得 CPU 版；也可以在“模型与工具”中指定已有兼容引擎。

## 开发检查与打包

```powershell
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\ruff.exe check animedialog main.py
.venv\Scripts\ruff.exe format animedialog main.py --check
.venv\Scripts\python.exe -m scripts.test_translation
.venv\Scripts\python.exe -m scripts.test_clips
.venv\Scripts\pyinstaller.exe AnimeDialog.spec --noconfirm
```

Windows 安装包使用 Inno Setup。安装该工具后，用其 `ISCC.exe` 编译：

```powershell
ISCC.exe scripts\installer.iss
```

本机已有 Inno Setup 位于 `.runtime/inno/` 时，也可运行 `.runtime\inno\ISCC.exe scripts\installer.iss`。EXE 产物位于 `dist/AnimeDialog/`，安装包位于 `release/`。打包前须准备好 `vendor/`、`licenses/` 及 `使用说明.html`。

`scripts/prepare_release_assets.py` 用于收集依赖许可、生成图标并下载 FFmpeg 上游源码归档。安装包构建完成后，运行 `.venv\Scripts\python.exe scripts\create_release.py` 生成源码压缩包及 SHA256 校验文件。

## 数据与项目结构

项目保存在独立文件夹中：`project.sqlite` 保存台词、人物、声音样本、任务与修改历史，`cache/` 保存检查点和兼容视频预览。视频默认引用原位置，移动后可重新关联；关闭软件后复制整个项目文件夹即可备份。

模型及设置默认位于 `%LOCALAPPDATA%\AnimeDialog`，模型目录可在界面调整。开发时可设置 `ANIMEDIALOG_HOME` 隔离测试数据。

| 路径 | 作用 |
| --- | --- |
| `animedialog/store.py` | SQLite 存储、修改历史、独立审核状态及建议版本 |
| `animedialog/pipeline.py`、`engines.py` | 处理进程、检查点、转写、字幕、OCR、声音与语义分析 |
| `animedialog/ui.py`、`workspace.py`、`dialogs.py` | 项目操作、播放器、台词编辑、菜单及快捷键 |
| `animedialog/exporters.py`、`importers.py` | 导出及旧成果、HTML / JSON 回导 |
| `animedialog/assets/review.html` | 离线 HTML 查看、视频定位与人工归类 |
| `animedialog/clips.py`、`media.py` | 片段列表、裁剪与视频合并 |
| `scripts/` | 工具获取与打包脚本 |
| `licenses/` | 第三方组件许可与来源记录 |

本地视频、作品数据、模型、缓存、开发环境和打包产物由 `.gitignore` 排除。人物及文字的自动结果仍需人工核对。

## 许可

AnimeDialog 源码使用 [MIT 许可](LICENSE)。第三方组件及单独下载的模型保留各自许可，见 [第三方说明](THIRD_PARTY_NOTICES.md) 与 `licenses/`。
