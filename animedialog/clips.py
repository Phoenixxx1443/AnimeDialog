"""A saved clip list; playback and exporting use the existing player and job queue."""

import uuid
from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, QSignalBlocker, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .domain import parse_stamp, stamp


class ClipPanel(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 8)
        tip = QLabel(
            "在“台词审核”中用 Ctrl / Shift 选句，按 Ctrl+Shift+K 添加。\n可跨集添加、重复添加；拖动片段或用按钮调整导出顺序。"
        )
        tip.setWordWrap(True)
        tip.setObjectName("muted")
        layout.addWidget(tip)
        tools = QHBoxLayout()
        tools.addWidget(window.push("add_clip", "添加所选台词"))
        back = QPushButton("返回选句  Ctrl+1")
        back.clicked.connect(window.focus_table)
        tools.addWidget(back)
        layout.addLayout(tools)
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        self.list.setToolTip("导出顺序由此列表决定；Ctrl / Shift 多选，双击预览")
        self.list.itemDoubleClicked.connect(lambda _: self.preview())
        self.list.itemSelectionChanged.connect(self.update_controls)
        self.list.model().rowsMoved.connect(self.persist)
        layout.addWidget(self.list, 1)
        tools = QHBoxLayout()
        self.buttons = {}
        for key, text, slot in [
            ("up", "上移", lambda: self.move(-1)),
            ("down", "下移", lambda: self.move(1)),
            ("remove", "移除", self.remove),
            ("time", "调整时间", self.edit_time),
            ("preview", "预览", self.preview),
        ]:
            button = QPushButton(text)
            button.clicked.connect(slot)
            tools.addWidget(button)
            self.buttons[key] = button
        layout.addLayout(tools)
        for key, slot in [
            ("Ctrl+Up", lambda: self.move(-1)),
            ("Ctrl+Down", lambda: self.move(1)),
            ("Delete", self.remove),
            ("Space", self.preview),
        ]:
            shortcut = QShortcut(QKeySequence(key), self.list)
            shortcut.setContext(Qt.WidgetShortcut)
            shortcut.activated.connect(slot)
        self.summary = QLabel("尚未添加片段")
        self.summary.setWordWrap(True)
        self.summary.setObjectName("muted")
        layout.addWidget(self.summary)
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setTextFormat(Qt.PlainText)
        self.detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.detail.setMaximumHeight(105)
        layout.addWidget(self.detail)
        choices = QHBoxLayout()
        choices.addWidget(QLabel("输出画质"))
        self.quality = QComboBox()
        for label, limit in [("最高 1080p", 1080), ("最高 720p", 720), ("原分辨率", 0)]:
            self.quality.addItem(label, limit)
        choices.addWidget(self.quality, 1)
        layout.addLayout(choices)
        note = QLabel(
            "输出 MP4，使用原视频与所选音轨，正常速度。\n保持画面比例；合并时以首段画幅和帧率为准，其他片段留边适配。"
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        layout.addWidget(note)
        tools = QHBoxLayout()
        for key, label, mode in [
            ("separate", "分段导出", "separate"),
            ("joined", "按顺序合并导出", "joined"),
        ]:
            button = QPushButton(label)
            button.setObjectName("primary" if mode == "joined" else "")
            button.clicked.connect(lambda _, mode=mode: self.export(mode))
            tools.addWidget(button)
            self.buttons[key] = button
        layout.addLayout(tools)
        self.output = QPushButton("打开导出目录")
        self.output.clicked.connect(self.open_output)
        layout.addWidget(self.output)
        self.setEnabled(False)

    def items(self):
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]

    def current(self):
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def load_project(self):
        with QSignalBlocker(self.list):
            self.list.clear()
            for clip in self.window.project.meta("clip_draft", []):
                self.append(clip)
        self.setEnabled(True)
        self.update_controls()

    def append(self, clip):
        item = QListWidgetItem()
        item.setData(Qt.UserRole, clip)
        self.list.addItem(item)

    def add_selected(self):
        window = self.window
        if not window.project or not window.save_editor():
            return
        ids = set(window.selected_ids())
        for row in window.table_model.rows:
            if row["id"] in ids:
                row = window.project.get("utterances", row["id"])
                self.append(
                    dict(
                        id=str(uuid.uuid4()),
                        row_id=row["id"],
                        episode_id=row["episode_id"],
                        start_ms=row["start_ms"],
                        end_ms=row["end_ms"],
                        text=row["translation"] or row["original"],
                    )
                )
        if ids:
            self.list.setCurrentRow(self.list.count() - 1)
            self.persist()
            window.right_tabs.setCurrentWidget(self)
            self.list.setFocus()

    def persist(self, *_):
        self.window.project.set_meta("clip_draft", self.items())
        self.update_controls()

    def update_controls(self):
        selected = self.list.selectedItems()
        indices = [self.list.row(item) for item in selected]
        count = self.list.count()
        for key in ["remove", "preview"]:
            self.buttons[key].setEnabled(bool(selected))
        self.buttons["time"].setEnabled(len(selected) == 1)
        self.buttons["up"].setEnabled(bool(indices) and min(indices) > 0)
        self.buttons["down"].setEnabled(bool(indices) and max(indices) < count - 1)
        for key in ["separate", "joined"]:
            self.buttons[key].setEnabled(bool(count))
        project = self.window.project
        for i, clip in enumerate(self.items()):
            episode = project.get("episodes", clip["episode_id"]) if project else None
            text = f"{i + 1:02d} · {(episode or {}).get('title', '视频已移除')}\n{stamp(clip['start_ms'])} → {stamp(clip['end_ms'])}\n{clip['text'].replace(chr(10), ' / ')[:70]}"
            self.list.item(i).setText(text)
            self.list.item(i).setToolTip(clip["text"])
        duration = sum(c["end_ms"] - c["start_ms"] for c in self.items())
        self.summary.setText(f"共 {count} 个片段 · 总时长 {stamp(duration)} · 自动保存")
        self.detail.setText((self.current() or {}).get("text", ""))
        self.output.setEnabled(bool(project and project.meta("clip_output")))

    def move(self, direction):
        selected = self.list.selectedItems()
        indices = sorted([self.list.row(item) for item in selected], reverse=direction > 0)
        if (
            not indices
            or min(indices) + direction < 0
            or max(indices) + direction >= self.list.count()
        ):
            return
        with QSignalBlocker(self.list):
            for i in indices:
                item = self.list.takeItem(i)
                self.list.insertItem(i + direction, item)
            for item in selected:
                item.setSelected(True)
            self.list.setCurrentItem(selected[0], QItemSelectionModel.NoUpdate)
        self.persist()

    def remove(self):
        with QSignalBlocker(self.list):
            for item in self.list.selectedItems():
                self.list.takeItem(self.list.row(item))
        self.window.clip_preview = None
        self.persist()

    def edit_time(self):
        if len(self.list.selectedItems()) != 1:
            return
        item = self.list.selectedItems()[0]
        clip = item.data(Qt.UserRole)
        dialog = QDialog(self)
        dialog.setWindowTitle("调整片段时间")
        layout = QFormLayout(dialog)
        start, end = QLineEdit(stamp(clip["start_ms"])), QLineEdit(stamp(clip["end_ms"]))
        layout.addRow("开始时间", start)
        layout.addRow("结束时间", end)
        layout.addRow(QLabel("格式：时:分:秒.毫秒；只修改片段，不改变原台词时间。"))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        layout.addRow(buttons)

        def accept():
            try:
                a, b = parse_stamp(start.text()), parse_stamp(end.text())
                ep = self.window.project.get("episodes", clip["episode_id"]) or {}
                if a < 0 or b <= a or ep.get("duration_ms", 0) and b > ep["duration_ms"]:
                    raise ValueError("时间须在视频范围内，且结束晚于开始。")
                clip.update(start_ms=a, end_ms=b)
                item.setData(Qt.UserRole, clip)
                self.window.clip_preview = None
                self.persist()
                dialog.accept()
            except (ValueError, OverflowError) as error:
                self.window.warn(error)

        buttons.accepted.connect(accept)
        buttons.rejected.connect(dialog.reject)
        dialog.exec()

    def preview(self):
        clip = self.current()
        if clip and self.window.save_editor():
            self.window.right_tabs.setCurrentWidget(self)
            self.window.clip_preview = clip
            self.window.load_video(clip["episode_id"])
            self.window.seek_video(clip["start_ms"])

    def export(self, mode):
        window = self.window
        clips = self.items()
        if not clips or not window.save_editor():
            return
        previous = window.project.meta("clip_output", str(Path.home() / "Videos"))
        if mode == "separate":
            parent = QFileDialog.getExistingDirectory(
                self, "选择保存位置（会新建片段子目录）", previous
            )
            path = str(Path(parent) / ("台词片段-" + uuid.uuid4().hex[:8])) if parent else ""
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, "按列表顺序合并导出", str(Path(previous) / "台词合辑.mp4"), "MP4 视频 (*.mp4)"
            )
            if path and Path(path).suffix.lower() != ".mp4":
                path += ".mp4"
            if path and Path(path).exists():
                window.warn("目标文件已存在，请使用新文件名，以保留已有视频。")
                return
        if not path:
            return
        for clip in clips:
            episode = window.project.get("episodes", clip["episode_id"])
            if not episode or not Path(episode["path"]).is_file():
                window.warn("原视频不存在，请在左侧重新关联后再导出。")
                return
            clip["audio_index"] = episode.get("audio_index")
        folder = Path(path) if mode == "separate" else Path(path).parent
        window.project.new_job(
            clips[0]["episode_id"],
            dict(
                task="clips",
                clips=clips,
                mode=mode,
                output=str(Path(path).resolve()),
                max_height=self.quality.currentData(),
            ),
        )
        window.project.set_meta("clip_output", str(folder.resolve()))
        self.update_controls()
        window.refresh_jobs()
        window.start_next_job()
        window.statusBar().showMessage("片段导出已加入队列，可在播放器下方暂停、继续或重试。", 8000)

    def open_output(self):
        folder = self.window.project.meta("clip_output")
        if folder and Path(folder).is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        else:
            self.window.statusBar().showMessage("导出目录尚未生成，请等待任务开始。", 5000)
