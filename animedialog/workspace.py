"""AnimeDialog 1.1 workspace, commands and review navigation.

Shortcuts belong to commands or to the video/table widgets. Text editors keep
Qt's native typing, selection, clipboard and undo shortcuts.
"""

from PySide6.QtCore import QAbstractTableModel, QByteArray, QEvent, QModelIndex, QSignalBlocker, Qt
from PySide6.QtGui import QAction, QColor, QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStyle,
    QTableView,
    QToolBar,
    QToolButton,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .domain import KINDS, needs_review, stamp
from .settings import save_settings, settings

STYLE = """
QMainWindow,QDialog { background:#f4f6fa; }
QWidget { font-family:"Microsoft YaHei","Segoe UI"; font-size:13px; color:#24344b; }
QMenuBar { background:#fff; padding:3px 8px; }
QMenuBar::item:selected,QMenu::item:selected { background:#e6edff; color:#244fad; }
QMenu { background:#fff; border:1px solid #d9e1ee; padding:6px; }
QMenu::item { padding:7px 22px; }
QToolBar { background:#fff; border:0; border-bottom:1px solid #dfe5ef; spacing:8px; padding:8px 12px; }
QToolButton,QPushButton { background:#fff; border:1px solid #d6deeb; border-radius:6px; padding:6px 10px; }
QToolButton:hover,QPushButton:hover { background:#edf2ff; border-color:#9bb1e5; }
QToolButton:pressed,QPushButton:pressed { background:#dfe8fc; }
QToolButton:disabled,QPushButton:disabled { color:#96a2b5; border-color:#e4e9f0; background:#f8f9fc; }
QToolButton#primary,QPushButton#primary { background:#315ac8; color:#fff; border-color:#315ac8; font-weight:600; }
QToolButton#primary:hover,QPushButton#primary:hover { background:#264baa; }
QPushButton#primary:disabled,QToolButton#primary:disabled { background:#b6c4e5; border-color:#b6c4e5; }
QLineEdit,QPlainTextEdit,QComboBox,QTreeWidget,QListWidget,QTableView {
    background:#fff; border:1px solid #dce3ee; border-radius:6px; padding:5px;
    selection-background-color:#dfe9ff; selection-color:#234a9c;
}
QLineEdit:focus,QPlainTextEdit:focus,QComboBox:focus,QTableView:focus { border-color:#6085dc; }
QTreeWidget,QListWidget,QTableView { outline:0; }
QTreeWidget::item,QListWidget::item { padding:6px 4px; }
QTreeWidget::item:selected,QListWidget::item:selected { background:#e3ecff; color:#21499d; border-radius:4px; }
QHeaderView::section { background:#eef2f8; padding:8px 6px; border:0; border-bottom:1px solid #dce3ee; font-weight:600; }
QTableView { gridline-color:#edf0f5; }
QGroupBox { border:1px solid #dce3ee; border-radius:8px; margin-top:12px; padding:10px; background:#fff; }
QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 6px; font-weight:600; }
QLabel#heading { font-size:21px; font-weight:600; color:#243b67; }
QLabel#muted { color:#74839a; font-size:12px; }
QLabel#badge { background:#e9efff; color:#3155a4; padding:5px 10px; border-radius:6px; }
QLabel#saveStatus { font-size:12px; color:#487365; }
QLabel#saveStatus[state="dirty"] { color:#976928; }
QLabel#saveStatus[state="error"] { color:#be4545; }
QLabel#videoHint { background:#182337; color:#d5deed; padding:8px; border-radius:6px; }
QScrollArea { border:0; background:transparent; }
QSplitter::handle { background:#e3e8f1; }
QSplitter::handle:hover { background:#b5c7ee; }
QProgressBar { border:0; border-radius:4px; background:#e9eef7; min-height:8px; max-height:8px; }
QProgressBar::chunk { background:#6484d4; border-radius:4px; }
QStatusBar { background:#fff; border-top:1px solid #dfe5ef; color:#63758e; }
QToolTip { background:#263650; color:#fff; border:0; padding:6px; }
"""


class TranscriptModel(QAbstractTableModel):
    headers = ["时间", "人物", "原文", "中文", "类型", "审核"]

    def __init__(self, parent):
        super().__init__(parent)
        self.rows = []
        self.names = {}
        self.playing_id = None

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 6

    def headerData(self, n, orientation, role):
        return self.headers[n] if orientation == Qt.Horizontal and role == Qt.DisplayRole else None

    def data(self, index, role):
        if not index.isValid():
            return None
        r = self.rows[index.row()]
        col = index.column()
        if role == Qt.DisplayRole:
            return [
                stamp(r["start_ms"])[:-4],
                "／".join(self.names.get(c, "待确认") for c in r["character_ids"]) or "待确认",
                r["original"].replace("\n", " / ")[:150],
                r["translation"].replace("\n", " / ")[:150],
                r["kind"],
                ("人物✓" if r["speaker_review"] == "confirmed" else "人物待核")
                + " · "
                + ("文字✓" if r["text_review"] == "confirmed" else "文字待核"),
            ][col]
        if role == Qt.ForegroundRole and col == 5:
            return QColor("#8a6a38" if needs_review(r) else "#39816a")
        if role == Qt.ToolTipRole:
            return r["original"] + "\n" + r["translation"] + "\n" + "；".join(r["flags"])
        if role == Qt.BackgroundRole and r["id"] == self.playing_id:
            return QColor("#e4edff")

    def set_rows(self, rows, characters):
        self.beginResetModel()
        self.rows = rows
        self.names = {c["id"]: c["name"] for c in characters}
        self.endResetModel()

    def row_index(self, row_id):
        return next((i for i, row in enumerate(self.rows) if row["id"] == row_id), -1)

    def playing(self, id):
        if self.playing_id == id:
            return
        prior = self.playing_id
        self.playing_id = id
        for i, r in enumerate(self.rows):
            if r["id"] in [prior, id]:
                self.dataChanged.emit(self.index(i, 0), self.index(i, 5), [Qt.BackgroundRole])


class WorkspaceMixin:
    def action(self, text, slot, shortcut=None):
        action = QAction(text, self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        return action

    def command(self, key, label, slot, shortcut=None, tip="", icon=None):
        action = self.action(label, slot, shortcut)
        action.setToolTip(tip or label)
        action.setStatusTip((tip or label) + (f"  ·  {shortcut}" if shortcut else ""))
        if icon is not None:
            action.setIcon(self.style().standardIcon(icon))
        self.commands[key] = action
        self.addAction(action)
        self.shortcut_entries.append((label, shortcut or "", tip))
        return action

    def build_toolbar(self):
        self.commands = {}
        self.shortcut_entries = []
        S = QStyle.StandardPixmap
        c = self.command
        c("new", "新建作品", self.new_project, "Ctrl+N", icon=S.SP_FileIcon)
        c("open", "打开项目", self.choose_project, "Ctrl+O", icon=S.SP_DirOpenIcon)
        c(
            "add_video",
            "添加视频",
            self.add_videos,
            "Ctrl+Shift+O",
            "批量添加同一作品的剧集",
            S.SP_FileDialogNewFolder,
        )
        c("import", "导入旧台词 / HTML", self.import_file, "Ctrl+I")
        c("save", "保存当前台词", self.save_editor, "Ctrl+S")
        c(
            "process",
            "开始处理",
            self.queue_all,
            "Ctrl+Shift+R",
            "处理选中的剧集；全部剧集会依次进入队列",
            S.SP_MediaPlay,
        )
        c(
            "export",
            "导出台词本",
            self.export,
            "Ctrl+Shift+E",
            "导出 Word、HTML、TXT、SRT 或 JSON",
            S.SP_DialogSaveButton,
        )
        c("models", "模型与工具", self.models, "Ctrl+Shift+M")
        c(
            "undo",
            "撤销项目操作",
            lambda: self.history(False),
            "Ctrl+Alt+Z",
            "撤销已保存的修改、删除、拆分或归类",
        )
        c("redo", "重做项目操作", lambda: self.history(True), "Ctrl+Alt+Y")
        c("add_row", "新增台词", self.add_row, "Ctrl+Shift+N", "在当前视频位置补充漏句")
        c("delete", "删除所选台词", self.delete_rows, "Ctrl+Shift+Delete", "删除可通过项目撤销恢复")
        c("split", "拆分当前台词", self.split_row)
        c("merge", "合并所选台词", self.merge_rows)
        c(
            "assign",
            "批量归类",
            self.assign_selected,
            "Ctrl+Shift+B",
            "多选台词，归入现有人物或新人物",
        )
        c("turns", "多人分句", self.turns)
        c("sample", "设为人物声音样本", self.voice_sample)
        c("retranscribe", "重新识别本句", self.retranscribe)
        c("match", "用声音样本推荐本集人物", self.match_voices)
        c("evidence", "查看完整归属依据", self.show_evidence)
        c("speaker", "确认当前人物", self.confirm_speaker, "F7", "只确认人物；多人台词请先逐句确认")
        c("text", "确认当前文字", self.confirm_text, "F8", "只确认原文与中文，不改变人物审核状态")
        c(
            "review_next",
            "文字校对并下一条",
            self.review_and_next,
            "Ctrl+Return",
            "保存文字校对结果，再跳到下一条可见台词",
        )
        self.commands["review_next"].setShortcuts(
            [QKeySequence("Ctrl+Return"), QKeySequence("Ctrl+Enter")]
        )
        c(
            "pending",
            "下一条待核",
            self.next_pending,
            "F9",
            "在当前筛选范围中查找；到末尾后从头继续",
        )
        c("previous", "上一句", lambda: self.navigate(-1), "Alt+Up")
        c("next", "下一句", lambda: self.navigate(1), "Alt+Down")
        c("play", "播放 / 暂停", self.play, "F5")
        c("back", "后退 2 秒", lambda: self.seek_relative(-2000), "Alt+Left")
        c("forward", "前进 2 秒", lambda: self.seek_relative(2000), "Alt+Right")
        c("loop", "循环本句", self.toggle_loop, "F6")
        c("preview", "生成兼容视频预览", self.preview_video)
        c("search", "搜索台词", self.focus_search, "Ctrl+F")
        c("table", "焦点移到台词列表", lambda: self.table.setFocus(), "Ctrl+1")
        c("original", "编辑原声文字", lambda: self.focus_text(self.original), "Ctrl+2")
        c("translation", "编辑中文对照", lambda: self.focus_text(self.translation), "Ctrl+3")
        c("person", "选择当前人物", self.focus_person, "Ctrl+4")
        c("reset_filters", "清除全部筛选", self.clear_filters)
        c("reset_layout", "恢复默认布局", self.reset_layout, "Ctrl+0")
        c("proposals", "识别与回导建议", self.proposals)
        c("statistics", "审核统计", self.review_statistics)
        c("shortcuts", "快捷键速查", self.show_shortcuts, "F1")
        c("help", "中文使用说明", self.help, "Shift+F1")
        menus = [
            ("文件", ["new", "open", "add_video", "import", "save", "export", "models"]),
            (
                "编辑",
                ["undo", "redo", None, "add_row", "delete", "split", "merge", "assign", "turns"],
            ),
            (
                "审核",
                [
                    "speaker",
                    "text",
                    "review_next",
                    "pending",
                    None,
                    "sample",
                    "match",
                    "retranscribe",
                    "evidence",
                    "proposals",
                    "statistics",
                ],
            ),
            ("播放", ["play", "previous", "next", "back", "forward", "loop", "preview"]),
            (
                "视图",
                [
                    "search",
                    "table",
                    "original",
                    "translation",
                    "person",
                    "reset_filters",
                    "reset_layout",
                ],
            ),
            ("帮助", ["shortcuts", "help"]),
        ]
        for title, keys in menus:
            menu = self.menuBar().addMenu(title)
            for key in keys:
                menu.addAction(self.commands[key]) if key else menu.addSeparator()
        bar = QToolBar("常用操作", self)
        bar.setMovable(False)
        bar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(bar)
        for key in ["new", "open", "add_video", "process", "export"]:
            if key in ["process", "export"]:
                bar.addSeparator()
            bar.addAction(self.commands[key])
        bar.widgetForAction(self.commands["process"]).setObjectName("primary")
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bar.addWidget(spacer)
        bar.addAction(self.commands["models"])
        bar.addAction(self.commands["shortcuts"])

    def push(self, key, label=None, primary=False):
        action = self.commands[key]
        widget = QPushButton(label or action.text())
        widget.setToolTip(action.statusTip())
        widget.clicked.connect(action.trigger)
        action.changed.connect(lambda: widget.setEnabled(action.isEnabled()))
        if primary:
            widget.setObjectName("primary")
        return widget

    def menu_button(self, text, actions):
        widget = QToolButton()
        widget.setText(text)
        widget.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(widget)
        for action in actions:
            menu.addAction(self.commands[action]) if isinstance(action, str) else menu.addAction(
                action
            )
        widget.setMenu(menu)
        return widget

    def build_layout(self):
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(12, 10, 12, 6)
        outer.setSpacing(8)
        self.setCentralWidget(root)
        header = QHBoxLayout()
        self.heading = QLabel("AnimeDialog")
        self.heading.setObjectName("heading")
        self.heading.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.heading.setMinimumWidth(150)
        self.project_summary = QLabel("导入视频 → 本地处理 → 对照审核 → 导出台词本")
        self.project_summary.setObjectName("muted")
        self.version_badge = QLabel("v" + __version__)
        self.version_badge.setObjectName("badge")
        header.addWidget(self.heading, 2)
        header.addWidget(self.project_summary, 1)
        header.addWidget(self.version_badge)
        outer.addLayout(header)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        outer.addWidget(self.splitter, 1)
        self.build_sidebar()
        self.build_player()
        self.build_transcript()
        self.reset_layout()
        self.restore_workspace()
        self.install_widget_shortcuts()
        self.update_commands()

    def build_sidebar(self):
        self.sidebar_splitter = QSplitter(Qt.Vertical)
        self.sidebar_splitter.setChildrenCollapsible(False)
        self.sidebar_splitter.setMinimumWidth(160)
        episode_box = QGroupBox("剧集")
        layout = QVBoxLayout(episode_box)
        self.episodes = QTreeWidget()
        self.episodes.setHeaderHidden(True)
        self.episodes.setIndentation(0)
        self.episodes.setMinimumHeight(70)
        self.episodes.itemSelectionChanged.connect(self.episode_selected)
        layout.addWidget(self.episodes, 1)
        controls = QHBoxLayout()
        controls.addWidget(self.push("add_video", "添加"))
        more = self.menu_button(
            "设置",
            [
                self.action("语言、音轨与字幕", self.episode_settings),
                self.action("重新关联视频", self.relink),
                self.action("上移剧集", lambda: self.move_episode(-1)),
                self.action("下移剧集", lambda: self.move_episode(1)),
            ],
        )
        controls.addWidget(more)
        layout.addLayout(controls)
        people_box = QGroupBox("作品人物")
        layout = QVBoxLayout(people_box)
        self.characters = QListWidget()
        self.characters.setMinimumHeight(70)
        self.characters.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.characters.setTextElideMode(Qt.ElideRight)
        self.characters.itemSelectionChanged.connect(self.character_selected)
        layout.addWidget(self.characters, 1)
        controls = QHBoxLayout()
        add = QPushButton("增加")
        add.clicked.connect(self.add_character)
        controls.addWidget(add)
        controls.addWidget(
            self.menu_button(
                "管理",
                [
                    self.action("重命名人物", self.rename_character),
                    self.action("合并人物", self.merge_character),
                    self.action("编辑别名", self.character_aliases),
                ],
            )
        )
        layout.addLayout(controls)
        self.sidebar_splitter.addWidget(episode_box)
        self.sidebar_splitter.addWidget(people_box)
        self.splitter.addWidget(self.sidebar_splitter)

    def build_player(self):
        self.center_splitter = QSplitter(Qt.Vertical)
        self.center_splitter.setChildrenCollapsible(False)
        self.center_splitter.setMinimumWidth(290)
        playback = QGroupBox("视频复核")
        layout = QVBoxLayout(playback)
        layout.setSpacing(6)
        self.video_frame = QWidget()
        self.video_frame.setMinimumHeight(130)
        self.video_frame.setStyleSheet("background:#182337;")
        self.video_frame.setAttribute(Qt.WA_StyledBackground, True)
        self.video = QVideoWidget(self.video_frame)
        self.video.setFocusPolicy(Qt.StrongFocus)
        self.video.setStyleSheet("background:#182337;")
        self.video.setAutoFillBackground(True)
        self.video.setAttribute(Qt.WA_StyledBackground, True)
        layout.addWidget(self.video_frame, 1)
        self.video_hint = QLabel("点击右侧台词定位视频")
        self.video_hint.setObjectName("videoHint")
        self.video_hint.setWordWrap(True)
        layout.addWidget(self.video_hint)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.6)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.player.positionChanged.connect(self.position_changed)
        self.player.durationChanged.connect(self.duration_changed)
        self.player.playbackStateChanged.connect(self.playback_changed)
        self.seek = QSlider(Qt.Horizontal)
        self.seek.setToolTip("拖动定位视频")
        self.seek.sliderMoved.connect(self.player.setPosition)
        layout.addWidget(self.seek)
        controls = QHBoxLayout()
        controls.addWidget(self.push("previous", "上句"))
        self.play_button = self.push("play", "播放", True)
        controls.addWidget(self.play_button)
        controls.addWidget(self.push("next", "下句"))
        self.loop = QCheckBox("循环")
        self.loop.setToolTip("循环当前整句 · F6")
        controls.addWidget(self.loop)
        layout.addLayout(controls)
        options = QHBoxLayout()
        options.addWidget(QLabel("倍速"))
        self.speed = QComboBox()
        self.speed.setToolTip("播放速度")
        for value in [0.5, 0.75, 1, 1.25, 1.5, 2, 3, 5]:
            self.speed.addItem(f"{value}×", value)
        self.speed.setCurrentIndex(2)
        self.speed.currentIndexChanged.connect(
            lambda: self.player.setPlaybackRate(self.speed.currentData())
        )
        options.addWidget(self.speed, 1)
        options.addWidget(QLabel("画幅"))
        self.aspect = QComboBox()
        self.aspect.setToolTip("原始比例保留视频宽高比；固定比例调整显示画幅；铺满填满播放区域")
        for label, ratio in [
            ("原始比例", None),
            ("16:9", 16 / 9),
            ("4:3", 4 / 3),
            ("1:1", 1),
            ("21:9", 21 / 9),
            ("铺满", 0),
        ]:
            self.aspect.addItem(label, ratio)
        self.aspect.currentIndexChanged.connect(self.update_video_aspect)
        options.addWidget(self.aspect, 2)
        layout.addLayout(options)
        self.video_frame.installEventFilter(self)
        self.update_video_aspect()
        info = QHBoxLayout()
        self.clock = QLabel("00:00:00 / 00:00:00")
        self.clock.setObjectName("muted")
        info.addWidget(self.clock, 1)
        self.mute = QCheckBox("静音")
        self.mute.toggled.connect(self.audio.setMuted)
        info.addWidget(self.mute)
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(60)
        self.volume.setMaximumWidth(65)
        self.volume.setToolTip("音量")
        self.volume.valueChanged.connect(lambda value: self.audio.setVolume(value / 100))
        info.addWidget(self.volume)
        layout.addLayout(info)
        self.center_splitter.addWidget(playback)
        queue = QGroupBox("处理队列")
        layout = QVBoxLayout(queue)
        layout.setSpacing(6)
        self.jobs = QListWidget()
        self.jobs.setMinimumHeight(50)
        layout.addWidget(self.jobs, 1)
        self.jobs.itemSelectionChanged.connect(self.update_job_controls)
        self.job_progress = QProgressBar()
        self.job_progress.setTextVisible(False)
        layout.addWidget(self.job_progress)
        controls = QHBoxLayout()
        self.job_buttons = {}
        for key, text, slot in [
            ("pause", "暂停", lambda: self.job_request("pause")),
            ("resume", "继续 / 重试", self.resume_job),
            ("cancel", "取消", lambda: self.job_request("cancel")),
        ]:
            widget = QPushButton(text)
            widget.clicked.connect(slot)
            self.job_buttons[key] = widget
            controls.addWidget(widget)
        layout.addLayout(controls)
        self.worker_status = QLabel("添加视频后，点击“开始处理”")
        self.worker_status.setWordWrap(True)
        self.worker_status.setObjectName("muted")
        self.worker_status.setMinimumWidth(0)
        layout.addWidget(self.worker_status)
        self.center_splitter.addWidget(queue)
        self.splitter.addWidget(self.center_splitter)

    def build_transcript(self):
        right = QWidget()
        layout = QVBoxLayout(right)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        right.setMinimumWidth(370)
        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.search.setPlaceholderText("搜索原文、中文、人物或备注  ·  Ctrl+F")
        self.search.textChanged.connect(lambda: self.filter_timer.start(200))
        layout.addWidget(self.search)
        filters = QHBoxLayout()
        self.kind = QComboBox()
        self.kind.addItem("全部类型", None)
        for kind in KINDS:
            self.kind.addItem(kind, kind)
        self.kind.currentIndexChanged.connect(self.refresh_rows)
        filters.addWidget(self.kind)
        self.review_filter = QComboBox()
        for text, value in [
            ("全部审核状态", None),
            ("人物待复核", "speaker"),
            ("文字待校对", "text"),
            ("任一待核", "any"),
        ]:
            self.review_filter.addItem(text, value)
        self.review_filter.currentIndexChanged.connect(self.refresh_rows)
        filters.addWidget(self.review_filter, 1)
        filters.addWidget(self.push("reset_filters", "清除筛选"))
        layout.addLayout(filters)
        self.scope_label = QLabel("全部剧集 · 全部人物")
        self.scope_label.setObjectName("muted")
        layout.addWidget(self.scope_label)
        self.scope_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.review_splitter = QSplitter(Qt.Vertical)
        self.review_splitter.setChildrenCollapsible(False)
        listing = QWidget()
        listing_layout = QVBoxLayout(listing)
        listing_layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableView()
        self.table_model = TranscriptModel(self)
        self.table.setModel(self.table_model)
        self.table.setMinimumHeight(80)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.horizontalHeader().setMinimumSectionSize(38)
        for col in [2, 3]:
            self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.Stretch)
        for col, width in [(0, 72), (1, 84), (4, 58), (5, 140)]:
            self.table.setColumnWidth(col, width)
        self.table.selectionModel().selectionChanged.connect(self.row_selected)
        self.table.selectionModel().currentChanged.connect(self.row_selected)
        self.table.doubleClicked.connect(lambda _: self.replay_current())
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.table_menu)
        listing_layout.addWidget(self.table, 1)
        tools = QHBoxLayout()
        self.row_count = QLabel("0 条台词")
        self.row_count.setObjectName("muted")
        tools.addWidget(self.row_count, 1)
        tools.addWidget(self.push("add_row", "新增"))
        tools.addWidget(self.push("assign", "批量归类"))
        tools.addWidget(self.menu_button("更多", ["merge", "delete", "proposals", "statistics"]))
        listing_layout.addLayout(tools)
        self.review_splitter.addWidget(listing)
        self.build_editor()
        layout.addWidget(self.review_splitter, 1)
        follow_row = QHBoxLayout()
        self.follow = QCheckBox("跟随播放高亮")
        self.follow.setChecked(True)
        self.follow.setToolTip("滚动到播放中的台词；编辑文字或多选台词时不会抢走位置")
        follow_row.addWidget(self.follow)
        follow_row.addStretch(1)
        follow_row.addWidget(self.push("pending", "下一待核  F9"))
        layout.addLayout(follow_row)
        self.splitter.addWidget(right)

    def build_editor(self):
        self.editor = QGroupBox("台词编辑")
        layout = QVBoxLayout(self.editor)
        layout.setSpacing(8)
        self.save_status = QLabel("自动保存")
        self.save_status.setObjectName("saveStatus")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(70)
        self.editor_scroll = scroll
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(8)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        times = QHBoxLayout()
        self.start = QLineEdit()
        self.end = QLineEdit()
        for text, widget in [("开始", self.start), ("结束", self.end)]:
            times.addWidget(QLabel(text))
            widget.setPlaceholderText("00:00:00.000")
            widget.setMinimumWidth(95)
            times.addWidget(widget, 1)
        body_layout.addLayout(times)
        texts = QHBoxLayout()
        self.original = QPlainTextEdit()
        self.translation = QPlainTextEdit()
        for label, widget, key in [
            ("原声文字 · Ctrl+2", self.original, "original"),
            ("中文对照 · Ctrl+3", self.translation, "translation"),
        ]:
            column = QVBoxLayout()
            column.setSpacing(4)
            column.addWidget(QLabel(label))
            widget.setMinimumHeight(84)
            widget.setMaximumHeight(110)
            widget.setTabChangesFocus(True)
            column.addWidget(widget, 1)
            texts.addLayout(column, 1)
        body_layout.addLayout(texts, 1)
        who = QHBoxLayout()
        who.addWidget(QLabel("人物"))
        self.person = QComboBox()
        self.person.setMinimumWidth(100)
        who.addWidget(self.person, 1)
        who.addWidget(self.push("turns", "多人分句"))
        layout.addLayout(who)
        review = QHBoxLayout()
        self.speaker_review = QCheckBox("人物已确认  F7")
        self.text_review = QCheckBox("文字已校对  F8")
        self.speaker_review.setToolTip("人物和文字分别审核；多个人物请打开“多人分句”")
        self.text_review.setToolTip("表示已人工核对原声文字与中文对照")
        review.addWidget(self.speaker_review)
        review.addWidget(self.text_review)
        review.addStretch(1)
        review.addWidget(self.save_status)
        review.addWidget(self.push("save", "保存"))
        layout.addLayout(review)
        notes = QHBoxLayout()
        self.row_kind = QComboBox()
        self.row_kind.addItems(KINDS)
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("备注（可选）")
        self.notes.setClearButtonEnabled(True)
        notes.addWidget(QLabel("类型"))
        notes.addWidget(self.row_kind)
        notes.addWidget(self.notes, 1)
        body_layout.addLayout(notes)
        evidence = QHBoxLayout()
        self.evidence = QLabel("尚无归属依据")
        self.evidence.setObjectName("muted")
        self.evidence.setWordWrap(True)
        self.evidence.setMaximumHeight(38)
        self.evidence.setMinimumWidth(0)
        evidence.addWidget(self.evidence, 1)
        evidence.addWidget(self.push("evidence", "查看依据"))
        body_layout.addLayout(evidence)
        actions = QHBoxLayout()
        actions.addWidget(self.push("review_next", "文字校对并下一条  Ctrl+Enter", True), 1)
        actions.addWidget(
            self.menu_button("更多操作", ["split", "sample", "match", "retranscribe", "preview"])
        )
        layout.addLayout(actions)
        self.review_splitter.addWidget(self.editor)
        self.editor.setEnabled(False)
        for field in [self.start, self.end, self.notes]:
            field.textEdited.connect(self.editor_changed)
        for field in [self.original, self.translation]:
            field.textChanged.connect(self.editor_changed)
        for field in [self.person, self.row_kind]:
            field.currentIndexChanged.connect(self.editor_changed)
        for field in [self.speaker_review, self.text_review]:
            field.toggled.connect(self.editor_changed)

    def install_widget_shortcuts(self):
        self.widget_shortcuts = []
        for widget in [self.table, self.video]:
            for key, slot in [
                ("Space", self.play),
                ("Ctrl+Z", lambda: self.history(False)),
                ("Ctrl+Y", lambda: self.history(True)),
            ]:
                shortcut = QShortcut(QKeySequence(key), widget)
                shortcut.setContext(Qt.WidgetWithChildrenShortcut)
                shortcut.activated.connect(slot)
                self.widget_shortcuts.append(shortcut)
        shortcut = QShortcut(QKeySequence("Delete"), self.table)
        shortcut.setContext(Qt.WidgetShortcut)
        shortcut.activated.connect(self.delete_rows)
        self.widget_shortcuts.append(shortcut)
        shortcut = QShortcut(QKeySequence("Escape"), self.search)
        shortcut.setContext(Qt.WidgetShortcut)
        shortcut.activated.connect(lambda: (self.search.clear(), self.table.setFocus()))
        self.widget_shortcuts.append(shortcut)

    def update_commands(self):
        project = bool(self.project)
        row = bool(self.current_row and not self.current_row.get("deleted"))
        ids = self.selected_ids() if hasattr(self, "table") else []
        for key in [
            "add_video",
            "import",
            "process",
            "export",
            "undo",
            "redo",
            "search",
            "proposals",
            "statistics",
            "reset_filters",
        ]:
            self.commands[key].setEnabled(project)
        for key in [
            "save",
            "split",
            "turns",
            "sample",
            "retranscribe",
            "evidence",
            "speaker",
            "text",
            "review_next",
            "person",
            "original",
            "translation",
        ]:
            self.commands[key].setEnabled(row)
        for key in ["delete", "assign"]:
            self.commands[key].setEnabled(project and bool(ids))
        self.commands["merge"].setEnabled(project and len(ids) > 1)
        self.commands["add_row"].setEnabled(
            project and bool(self.current_episode or self.playing_episode)
        )
        for key in ["match", "preview"]:
            self.commands[key].setEnabled(project and bool(self.current_episode or row))
        for key in ["previous", "next", "pending"]:
            self.commands[key].setEnabled(project and bool(self.table_model.rows))
        self.row_count.setText(f"{len(self.table_model.rows)} 条 · 已选 {len(ids)} 条")

    def set_save_status(self, text="已保存", state="saved"):
        self.save_status.setText(text)
        self.save_status.setProperty("state", state)
        if state != "error":
            self.save_status.setToolTip("修改后约 0.65 秒自动保存，也可按 Ctrl+S")
        self.save_status.style().unpolish(self.save_status)
        self.save_status.style().polish(self.save_status)

    def focus_search(self):
        self.search.setFocus()
        self.search.selectAll()

    def focus_text(self, field):
        field.setFocus()
        # ensureWidgetVisible uses a focused text editor's caret rectangle;
        # expose the full editor instead, so Ctrl+2/3 is useful on small screens.
        center = field.mapTo(self.editor_scroll.widget(), field.rect().center())
        self.editor_scroll.ensureVisible(center.x(), center.y(), 4, field.height() // 2 + 4)

    def focus_person(self):
        self.person.setFocus()
        self.person.showPopup()

    def toggle_loop(self):
        self.loop.setChecked(not self.loop.isChecked())

    def eventFilter(self, watched, event):
        if watched is self.video_frame and event.type() == QEvent.Resize:
            self.update_video_aspect()
        return super().eventFilter(watched, event)

    def update_video_aspect(self):
        rect = self.video_frame.rect()
        ratio = self.aspect.currentData()
        self.video.setAspectRatioMode(Qt.KeepAspectRatio if ratio is None else Qt.IgnoreAspectRatio)
        if ratio:
            width = min(rect.width(), round(rect.height() * ratio))
            height = min(rect.height(), round(rect.width() / ratio))
            self.video.setGeometry(
                (rect.width() - width) // 2, (rect.height() - height) // 2, width, height
            )
        else:
            self.video.setGeometry(rect)

    def playback_changed(self, state):
        self.play_button.setText("暂停" if state == QMediaPlayer.PlayingState else "播放")

    def seek_relative(self, delta):
        if self.player.isSeekable():
            self.player.setPosition(
                max(0, min(self.player.duration(), self.player.position() + delta))
            )

    def replay_current(self):
        if self.current_row and self.save_editor():
            self.load_video(self.current_row["episode_id"])
            self.seek_video(max(0, self.current_row["start_ms"] - 300))

    def select_record(self, row_id):
        index = self.table_model.row_index(row_id)
        if index < 0 or not self.save_editor():
            return False
        self.table.selectRow(index)
        self.table.scrollTo(self.table_model.index(index, 0))
        return True

    def is_pending(self, row):
        return needs_review(row, self.review_filter.currentData())

    def next_pending(self):
        if not self.save_editor():
            return
        rows = self.table_model.rows
        if not rows:
            return
        current = self.table_model.row_index((self.current_row or {}).get("id"))
        for offset in range(1, len(rows) + 1):
            row = rows[(current + offset) % len(rows)]
            if self.is_pending(row):
                repeated = row["id"] == (self.current_row or {}).get("id")
                self.select_record(row["id"])
                if repeated:
                    self.replay_current()
                return
        self.statusBar().showMessage("当前筛选范围已无待核台词", 5000)

    def confirm_speaker(self):
        if not self.current_row or not self.save_editor():
            return False
        row = self.current_row
        if not (
            self.person.currentData()
            or row["turns"]
            and all(t.get("character_id") and t.get("review") == "confirmed" for t in row["turns"])
        ):
            self.statusBar().showMessage("请先选择一个人物；多人台词需在“多人分句”中分别确认", 6000)
            return False
        self.speaker_review.setChecked(True)
        self.editor_changed()
        return self.save_editor()

    def confirm_text(self):
        if not self.current_row or not self.save_editor():
            return False
        self.text_review.setChecked(True)
        self.editor_changed()
        return self.save_editor()

    def review_and_next(self):
        if not self.current_row:
            return
        rows = self.table_model.rows
        current = self.table_model.row_index(self.current_row["id"])
        next_id = rows[current + 1]["id"] if 0 <= current < len(rows) - 1 else None
        if not self.confirm_text():
            return
        # Reapply pending/search filters only after saving the human review.
        self.refresh_rows()
        if next_id and self.select_record(next_id):
            return
        if self.review_filter.currentData():
            self.next_pending()
        else:
            self.statusBar().showMessage("已校对当前文字，已到当前列表末尾", 5000)

    def reset_transcript_filters(self):
        with (
            QSignalBlocker(self.kind),
            QSignalBlocker(self.review_filter),
            QSignalBlocker(self.search),
        ):
            self.kind.setCurrentIndex(0)
            self.review_filter.setCurrentIndex(0)
            self.search.clear()

    def clear_filters(self):
        if not self.project or not self.save_editor():
            return
        self.reset_transcript_filters()
        self.current_episode = None
        with QSignalBlocker(self.characters):
            self.characters.setCurrentRow(0)
        self.refresh_sidebar()
        self.refresh_rows()

    def character_aliases(self):
        if self.chosen_character() and self.save_editor():
            self.edit_character_details(self.chosen_character())
            self.refresh_sidebar()

    def table_menu(self, point):
        self.update_commands()
        menu = QMenu(self.table)
        for key in [
            "speaker",
            "text",
            "review_next",
            "assign",
            "turns",
            "split",
            "merge",
            "delete",
            "evidence",
        ]:
            menu.addAction(self.commands[key])
        menu.exec(self.table.viewport().mapToGlobal(point))

    def show_evidence(self):
        if not self.current_row:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("人物归属依据与复核提示")
        dialog.resize(650, 420)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        row = self.current_row
        text.setPlainText(
            "归属依据\n"
            + "\n".join(row["evidence"] or ["尚无可靠依据"])
            + "\n\n复核提示\n"
            + "\n".join(row["flags"] or ["无额外提示"])
        )
        layout.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("关闭")
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def show_shortcuts(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("AnimeDialog 1.1 · 快捷键速查")
        dialog.resize(660, 670)
        layout = QVBoxLayout(dialog)
        note = QLabel(
            "F5 播放 · F7 确认人物 · F8 校对文字 · F9 下一待核\nCtrl+Enter 校对文字并下一条；人物审核状态单独保存。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        table = QTreeWidget()
        table.setHeaderLabels(["操作", "快捷键"])
        table.setRootIsDecorated(False)
        from PySide6.QtWidgets import QTreeWidgetItem

        for label, key, tip in self.shortcut_entries:
            if key:
                item = QTreeWidgetItem([label, key.replace("Return", "Enter")])
                item.setToolTip(0, tip)
                table.addTopLevelItem(item)
        for label, key in [
            ("播放 / 暂停（列表或视频焦点）", "Space"),
            ("撤销 / 重做文字输入（文字框焦点）", "Ctrl+Z / Ctrl+Y"),
            ("撤销 / 重做项目操作（列表或视频焦点）", "Ctrl+Z / Ctrl+Y"),
            ("删除台词（列表焦点）", "Delete"),
            ("清空搜索并返回列表（搜索框焦点）", "Esc"),
        ]:
            table.addTopLevelItem(QTreeWidgetItem([label, key]))
        table.header().setSectionResizeMode(0, QHeaderView.Stretch)
        table.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        layout.addWidget(table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("关闭")
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def reset_layout(self):
        self.splitter.setSizes([210, 430, 770])
        self.sidebar_splitter.setSizes([320, 380])
        self.center_splitter.setSizes([440, 260])
        self.review_splitter.setSizes([240, 470])

    def restore_workspace(self):
        state = settings().get("workspace", {})
        try:
            if state.get("geometry"):
                self.restoreGeometry(QByteArray.fromBase64(state["geometry"].encode("ascii")))
            for key, widget in [
                ("columns", self.splitter),
                ("sidebar", self.sidebar_splitter),
                ("player", self.center_splitter),
                ("review", self.review_splitter),
            ]:
                if state.get(key):
                    widget.restoreState(QByteArray.fromBase64(state[key].encode("ascii")))
            self.follow.setChecked(bool(state.get("follow", True)))
            self.volume.setValue(max(0, min(100, int(state.get("volume", 60)))))
            speed = self.speed.findData(state.get("speed", 1))
            if speed >= 0:
                self.speed.setCurrentIndex(speed)
            self.aspect.setCurrentIndex(max(0, self.aspect.findData(state.get("aspect_ratio"))))
        except (ValueError, TypeError, AttributeError):
            pass

    def save_workspace(self):
        state = {
            "geometry": bytes(self.saveGeometry().toBase64()).decode("ascii"),
            "follow": self.follow.isChecked(),
            "volume": self.volume.value(),
            "speed": self.speed.currentData(),
            "aspect_ratio": self.aspect.currentData(),
        }
        for key, widget in [
            ("columns", self.splitter),
            ("sidebar", self.sidebar_splitter),
            ("player", self.center_splitter),
            ("review", self.review_splitter),
        ]:
            state[key] = bytes(widget.saveState().toBase64()).decode("ascii")
        value = settings()
        value["workspace"] = state
        save_settings(value)

    def update_job_controls(self):
        job_id = self.selected_job() if self.project else None
        job = self.project.get("jobs", job_id) if job_id else None
        state = job["state"] if job else None
        for key, enabled in [
            ("pause", state in ["running", "queued"]),
            ("resume", state in ["paused", "failed", "cancelled"]),
            ("cancel", state in ["running", "queued", "paused", "failed"]),
        ]:
            self.job_buttons[key].setEnabled(enabled)
        self.job_progress.setValue(round(job.get("progress", 0)) if job else 0)
        self.job_progress.setToolTip(
            (job.get("stage", "") + f" · {job.get('progress', 0):.0f}%") if job else "尚无处理任务"
        )
