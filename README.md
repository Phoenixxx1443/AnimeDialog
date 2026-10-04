# AnimeDialog · 本地视频台词整理与人物审核

把动漫或电视剧视频整理成按人物分类的双语台词本，并在同一窗口中播放、审核、修改和导出。

**当前版本：1.1.2 · Windows 11 x64 · Python 3.12+ · MIT**

AnimeDialog 在本机完成视频处理。首次使用可下载模型，也可导入已有模型；模型准备好后，识别、翻译和人物建议均可离线运行。

## 功能

- **导入多集视频：** 支持 MP4、MKV、MOV 等格式，同一作品的多集共享人物、别名和声音样本。
- **生成双语台词：** 识别原声及时间轴，优先利用内嵌或附加字幕；可调整字幕区域后提取烧录字幕。默认生成原文与简体中文对照，中文原声保留一份原文。
- **提出人物归属建议：** 结合声音特征、称呼和上下文提出姓名与归属候选，保留依据；证据不足时使用临时人物名，等待人工确认。
- **对照视频审核：** 点击台词定位视频，搜索、筛选、循环本句，编辑原文、译文、人物、时间和备注；支持新增、删除、拆分、合并及批量归类。
- **保存人工修改：** 人物确认与文字校对分别记录，支持自动保存、撤销和重做；重新识别及 HTML 回导结果进入建议比较，人工修改不会自动被覆盖。
- **导出台词本：** 支持 Word、离线 HTML、TXT、SRT 和 JSON。HTML 可选择本地视频进行人工归类，保存后重新导入软件。
- **管理任务与模型：** 队列支持暂停、继续、取消和重试；已完成阶段保存检查点，模型支持本地导入、下载恢复及完整性校验。

1.1.2 的播放器支持 **0.5×、0.75×、1×、1.25×、1.5×、2×、3×、5×**，以及 **原始比例、16:9、4:3、1:1、21:9、铺满**。退出软件后保存倍速、画幅、音量和布局。

## 安装

Windows 安装包包含 Python、Qt、播放器及处理引擎，使用者无需另装 Python。大型模型单独下载或导入。

从 [Releases](https://github.com/Phoenixxx1443/AnimeDialog/releases/latest) 下载：

- **[Windows 安装包](https://github.com/Phoenixxx1443/AnimeDialog/releases/download/v1.1.2/AnimeDialog-1.1.2-Windows-x64-Setup.exe)**：下载后运行即可安装。
- **[源码压缩包](https://github.com/Phoenixxx1443/AnimeDialog/releases/download/v1.1.2/AnimeDialog-1.1.2-Source.zip)**：解压后可从源码运行或自行打包。

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

### 4. 导出或回导

点击“导出台词本”，选择格式、范围及时间顺序或人物分组。SRT 按剧集分别导出，可选原文、中文或双语。

导出的 HTML 可离线打开，选择本地对应视频后进行复核、编辑及人物归类。网页中点击“保存 HTML 副本”，再在软件中使用“文件 → 导入旧台词 / HTML”回导；有修改冲突时先比较，再决定是否接受。

详细说明见 [中文使用说明](使用说明.html)，下载后可用浏览器打开。

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

私有仓库需要使用有权限的 GitHub 账号克隆。`requirements-lock.txt` 记录本次 Windows 构建依赖；`bootstrap_tools.py` 从发布者下载 FFmpeg、FFprobe、Whisper.cpp 和 llama.cpp 到 `vendor/`。应用启动后，在“模型与工具”中另行准备模型。

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
| `scripts/` | 工具获取与打包脚本 |
| `licenses/` | 第三方组件许可与来源记录 |

本地视频、作品数据、模型、缓存、开发环境和打包产物由 `.gitignore` 排除。人物及文字的自动结果仍需人工核对。

## 许可

AnimeDialog 源码使用 [MIT 许可](LICENSE)。第三方组件及单独下载的模型保留各自许可，见 [第三方说明](THIRD_PARTY_NOTICES.md) 与 `licenses/`。
