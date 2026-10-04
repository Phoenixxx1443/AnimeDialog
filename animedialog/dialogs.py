from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .domain import clone, parse_stamp, stamp
from .media import frame
from .models import MODEL_SPECS, digest, download_model, import_model, model_path
from .settings import executable, models_root, save_settings, settings


def button(text, slot):
    b = QPushButton(text)
    b.clicked.connect(slot)
    return b


def confirmation_buttons():
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.button(QDialogButtonBox.Ok).setText("确定")
    buttons.button(QDialogButtonBox.Ok).setObjectName("primary")
    buttons.button(QDialogButtonBox.Cancel).setText("取消")
    return buttons


class WorkThread(QThread):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(int, str)

    def __init__(self, action, parent=None):
        super().__init__(parent)
        self.action = action
        self.cancelled = False

    def run(self):
        try:
            self.done.emit(self.action(self))
        except Exception as e:
            self.failed.emit(str(e))


class ModelsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("模型与工具")
        self.resize(820, 620)
        self.threads = []
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("模型下载完成后可离线处理。模型文件较大；可以导入此前使用的模型。"))
        form = QFormLayout()
        self.directory = QLineEdit(str(models_root()))
        form.addRow("模型保存位置", self.directory)
        layout.addLayout(form)
        layout.addWidget(button("选择模型文件夹", self.choose_dir))
        self.table = QTableWidget(len(MODEL_SPECS), 5)
        self.table.setHorizontalHeaderLabels(["模型", "状态", "下载", "导入已有模型", "完整性"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        for col, width in [(2, 110), (3, 115), (4, 80)]:
            self.table.setColumnWidth(col, width)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(44)
        for i, (key, spec) in enumerate(MODEL_SPECS.items()):
            self.table.setItem(i, 0, QTableWidgetItem(spec["name"]))
            self.table.setCellWidget(i, 2, button("下载 / 续传", lambda _, k=key: self.download(k)))
            self.table.setCellWidget(i, 3, button("导入", lambda _, k=key: self.import_file(k)))
            self.table.setCellWidget(i, 4, button("校验", lambda _, k=key: self.verify(k)))
        layout.addWidget(self.table)
        self.update_models()
        tools = QFormLayout()
        self.tool_inputs = {}
        for name in ["ffmpeg", "ffprobe", "whisper-cli", "llama-server"]:
            box = QWidget()
            line = QHBoxLayout(box)
            line.setContentsMargins(0, 0, 0, 0)
            try:
                value = executable(name)
            except FileNotFoundError:
                value = ""
            edit = QLineEdit(value)
            self.tool_inputs[name] = edit
            line.addWidget(edit)
            line.addWidget(button("选择", lambda _, e=edit: self.choose_tool(e)))
            tools.addRow(name, box)
        layout.addLayout(tools)
        self.bar = QProgressBar()
        layout.addWidget(self.bar)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        bottom = QHBoxLayout()
        bottom.addWidget(button("取消当前下载", self.cancel_download))
        save_button = button("保存设置", self.save)
        save_button.setObjectName("primary")
        bottom.addWidget(save_button)
        layout.addLayout(bottom)

    def choose_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "选择模型保存目录", self.directory.text())
        if folder:
            self.directory.setText(folder)
            self.save(close=False)

    def choose_tool(self, edit):
        p, _ = QFileDialog.getOpenFileName(self, "选择程序", "", "程序 (*.exe)")
        if p:
            edit.setText(p)

    def update_models(self):
        for i, key in enumerate(MODEL_SPECS):
            p = model_path(key)
            self.table.setItem(
                i,
                1,
                QTableWidgetItem(
                    f"{p.stat().st_size / 1024**2:.0f} MB 已就绪" if p.exists() else "未安装"
                ),
            )
            manifest = p.with_suffix(p.suffix + ".json")
            if manifest.exists():
                self.table.item(i, 1).setToolTip(manifest.read_text(encoding="utf8"))

    def verify(self, key):
        def work(t):
            import json

            from .models import verify_format

            p = model_path(key)
            verify_format(p, key)
            manifest = p.with_suffix(p.suffix + ".json")
            if not manifest.exists():
                raise ValueError("缺少原校验信息，请重新导入以建立记录")
            if digest(p) != json.loads(manifest.read_text(encoding="utf8"))["sha256"]:
                raise ValueError("模型校验不一致，请重新下载或导入")
            return str(p)

        self.start(work)

    def start(self, action):
        if any(t.isRunning() for t in self.threads):
            QMessageBox.information(self, "处理中", "请等待当前模型操作结束。")
            return
        t = WorkThread(action, self)
        self.threads.append(t)
        t.progress.connect(
            lambda value, text: (self.bar.setValue(value), self.message.setText(text))
        )
        t.done.connect(
            lambda result: (self.message.setText("模型已验证并保存"), self.update_models())
        )
        t.failed.connect(self.message.setText)
        t.start()

    def download(self, key):
        self.save(close=False)

        def work(t):
            return str(
                download_model(
                    key,
                    lambda done, total: t.progress.emit(
                        round(done * 100 / total) if total else 0,
                        f"{done / 1024**2:.0f} / {total / 1024**2:.0f} MB",
                    ),
                    lambda: t.cancelled,
                )
            )

        self.start(work)

    def import_file(self, key):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择 " + MODEL_SPECS[key]["name"], "", "模型 (*.bin *.gguf *.onnx)"
        )
        if p:
            self.save(close=False)
            self.start(lambda t: str(import_model(key, p)))

    def cancel_download(self):
        for t in self.threads:
            t.cancelled = True

    def save(self, close=True):
        s = settings()
        s["models_dir"] = self.directory.text().strip()
        s.update({n: e.text().strip() for n, e in self.tool_inputs.items() if e.text().strip()})
        save_settings(s)
        self.update_models()
        if close and not any(t.isRunning() for t in self.threads):
            self.accept()

    def closeEvent(self, event):
        if any(t.isRunning() for t in self.threads):
            self.message.setText("下载进行中；取消后等待当前数据块结束再关闭。")
            self.cancel_download()
            event.ignore()
        else:
            super().closeEvent(event)

    def reject(self):
        if any(t.isRunning() for t in self.threads):
            self.cancel_download()
            self.message.setText("正在停止下载，请稍后关闭。")
        else:
            super().reject()


class EpisodeDialog(QDialog):
    def __init__(self, episode, parent):
        super().__init__(parent)
        self.setWindowTitle("剧集与识别设置")
        self.resize(740, 640)
        self.episode = clone(episode)
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        form = QFormLayout()
        self.title = QLineEdit(episode["title"])
        form.addRow("剧集名称", self.title)
        self.language = QComboBox()
        for label, value in [
            ("自动检测", "auto"),
            ("日语", "ja"),
            ("中文", "zh"),
            ("英语", "en"),
            ("韩语", "ko"),
            ("法语", "fr"),
            ("德语", "de"),
            ("西班牙语", "es"),
        ]:
            self.language.addItem(label, value)
        self.language.setCurrentIndex(
            max(0, self.language.findData(episode.get("language", "auto")))
        )
        form.addRow("原声语言", self.language)
        self.audio = QComboBox()
        self.sub = QComboBox()
        self.sub.addItem("不使用内嵌字幕", None)
        for s in episode.get("metadata", {}).get("streams", []):
            label = f"轨道 {s['index']} · {s.get('codec_name', '')} · {s.get('tags', {}).get('language', '')} · {s.get('tags', {}).get('title', '')}"
            if s["codec_type"] == "audio":
                self.audio.addItem(label, s["index"])
            elif s["codec_type"] == "subtitle":
                self.sub.addItem(label, s["index"])
        if not self.audio.count():
            self.audio.addItem("自动选择第一个音轨", None)
        self.audio.setCurrentIndex(max(0, self.audio.findData(episode.get("audio_index"))))
        if episode.get("subtitle_indices"):
            self.sub.setCurrentIndex(max(0, self.sub.findData(episode["subtitle_indices"][0])))
        form.addRow("声音轨道", self.audio)
        form.addRow("内嵌字幕", self.sub)
        self.attached = QPlainTextEdit("\n".join(episode.get("attached", [])))
        self.attached.setMaximumHeight(65)
        form.addRow("外挂字幕路径", self.attached)
        form.addRow("", button("添加 SRT / ASS 字幕", self.attach))
        layout.addLayout(form)
        self.attached_target = QComboBox()
        for label, value in [
            ("自动判断字幕语言", "auto"),
            ("原声字幕（替换识别文字）", "original"),
            ("中文字幕（作为对照）", "translation"),
        ]:
            self.attached_target.addItem(label, value)
        self.attached_target.setCurrentIndex(
            max(0, self.attached_target.findData(episode.get("attached_target", "auto")))
        )
        layout.addWidget(self.attached_target)
        self.speakers = QCheckBox("自动分离不同声音")
        self.speakers.setChecked(episode.get("options", {}).get("speakers", True))
        self.semantic = QCheckBox("生成中文翻译和人物姓名候选")
        self.semantic.setChecked(episode.get("options", {}).get("semantic", True))
        self.ocr = QCheckBox("提取画面中的烧录中文字幕")
        self.ocr.setChecked(bool(episode.get("ocr_regions")))
        for check in [self.speakers, self.semantic, self.ocr]:
            layout.addWidget(check)
        self.ocr_target = QComboBox()
        self.ocr_target.addItem("烧录字幕为中文对照", "translation")
        self.ocr_target.addItem("烧录字幕为原声文字", "original")
        self.ocr_target.setCurrentIndex(
            max(0, self.ocr_target.findData(episode.get("ocr_target", "translation")))
        )
        layout.addWidget(self.ocr_target)
        layout.addWidget(
            QLabel("字幕区域使用比例坐标：左、上、宽、高；每行一个区域，可同时提取顶部和底部。")
        )
        self.regions = QPlainTextEdit(
            "\n".join(", ".join(str(v) for v in r) for r in episode.get("ocr_regions", []))
            or "0, 0.78, 1, 0.20"
        )
        self.regions.setMaximumHeight(50)
        layout.addWidget(self.regions)
        self.preview = QLabel("点击“查看字幕区域”预览视频中的识别范围")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(180)
        layout.addWidget(self.preview)
        line = QHBoxLayout()
        self.preview_time = QLineEdit("00:00:30")
        line.addWidget(self.preview_time)
        line.addWidget(button("查看字幕区域", self.show_frame))
        layout.addLayout(line)
        buttons = confirmation_buttons()
        buttons.accepted.connect(self.accept_checked)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def attach(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "添加外挂字幕", "", "字幕 (*.srt *.ass *.ssa)"
        )
        if paths:
            self.attached.setPlainText(self.attached.toPlainText() + "\n" + "\n".join(paths))

    def get_regions(self):
        rs = []
        for line in self.regions.toPlainText().splitlines():
            if not line.strip():
                continue
            values = [float(x) for x in line.split(",")]
            if (
                len(values) != 4
                or any(v < 0 for v in values)
                or values[0] + values[2] > 1
                or values[1] + values[3] > 1
                or not values[2]
                or not values[3]
            ):
                raise ValueError("区域应为四个 0～1 的比例值，且不得超出画面")
            rs.append(values)
        return rs

    def show_frame(self):
        try:
            from PySide6.QtGui import QColor, QPainter, QPen

            parent = self.parent()
            path = parent.project.folder / "cache" / "region-preview.jpg"
            frame(self.episode["path"], path, parse_stamp(self.preview_time.text()))
            pix = QPixmap(str(path))
            painter = QPainter(pix)
            painter.setPen(QPen(QColor("#ffcc33"), 3))
            for x, y, w, h in self.get_regions():
                painter.drawRect(
                    round(x * pix.width()),
                    round(y * pix.height()),
                    round(w * pix.width()),
                    round(h * pix.height()),
                )
            painter.end()
            self.preview.setPixmap(
                pix.scaled(680, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        except Exception as e:
            QMessageBox.warning(self, "无法预览", str(e))

    def accept_checked(self):
        try:
            self.episode.update(
                title=self.title.text(),
                language=self.language.currentData(),
                audio_index=self.audio.currentData(),
                subtitle_indices=[self.sub.currentData()]
                if self.sub.currentData() is not None
                else [],
                attached=[x.strip() for x in self.attached.toPlainText().splitlines() if x.strip()],
                attached_target=self.attached_target.currentData(),
                ocr_regions=self.get_regions() if self.ocr.isChecked() else [],
            )
            for p in self.episode["attached"]:
                if not Path(p).is_file():
                    raise ValueError("外挂字幕不存在：" + p)
            self.episode["ocr_target"] = self.ocr_target.currentData()
            self.options = dict(
                speakers=self.speakers.isChecked(),
                semantic=self.semantic.isChecked(),
                ocr=self.ocr.isChecked(),
            )
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "设置无效", str(e))


class TurnsDialog(QDialog):
    def __init__(self, row, characters, parent):
        super().__init__(parent)
        self.setWindowTitle("多人分句归属与时间")
        self.resize(950, 560)
        self.row = clone(row)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel("分句时间可留空；留空表示使用整段回看定位，不代表每句已经确定时间。")
        )
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["中文分句", "人物", "开始时间（可空）", "结束时间（可空）", "人物已确认"]
        )
        layout.addWidget(self.table)
        self.characters = characters
        turns = row.get("turns") or [
            dict(text=t, character_id=None, start_ms=None, end_ms=None, review="pending")
            for t in (row["translation"] or row["original"]).splitlines()
            if t.strip()
        ]
        for turn in turns:
            self.add(turn)
        layout.addWidget(
            button(
                "增加分句",
                lambda: self.add(
                    dict(text="", character_id=None, start_ms=None, end_ms=None, review="pending")
                ),
            )
        )
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        buttons = confirmation_buttons()
        buttons.accepted.connect(self.accept_checked)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def add(self, t):
        i = self.table.rowCount()
        self.table.insertRow(i)
        self.table.setItem(i, 0, QTableWidgetItem(t.get("text", "")))
        combo = QComboBox()
        combo.addItem("待确认", None)
        for c in self.characters:
            combo.addItem(c["name"], c["id"])
        combo.setCurrentIndex(max(0, combo.findData(t.get("character_id"))))
        self.table.setCellWidget(i, 1, combo)
        for col, key in [(2, "start_ms"), (3, "end_ms")]:
            self.table.setItem(
                i, col, QTableWidgetItem(stamp(t[key]) if t.get(key) is not None else "")
            )
        check = QCheckBox()
        check.setChecked(t.get("review") == "confirmed")
        self.table.setCellWidget(i, 4, check)

    def accept_checked(self):
        try:
            from .domain import validate

            turns = []
            for i in range(self.table.rowCount()):
                text = self.table.item(i, 0).text().strip()
                if not text:
                    continue
                cid = self.table.cellWidget(i, 1).currentData()
                a = self.table.item(i, 2).text().strip()
                b = self.table.item(i, 3).text().strip()
                turns.append(
                    dict(
                        text=text,
                        character_id=cid,
                        start_ms=parse_stamp(a) if a else None,
                        end_ms=parse_stamp(b) if b else None,
                        review="confirmed"
                        if cid and self.table.cellWidget(i, 4).isChecked()
                        else "pending",
                    )
                )
            self.row["turns"] = turns
            validate(self.row)
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "分句无效", str(e))


class ExportDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("导出台词本")
        layout = QFormLayout(self)
        self.format = QComboBox()
        self.format.addItems(
            [
                "Word (.docx)",
                "离线审核 HTML (.html)",
                "文本 (.txt)",
                "字幕 (.srt)",
                "项目台词 JSON (.json)",
            ]
        )
        self.scope = QComboBox()
        self.scope.addItems(["当前筛选结果", "全部作品", "当前剧集"])
        self.group = QCheckBox("按人物分组（字幕仍按时间排序）")
        self.language = QComboBox()
        self.language.addItem("原文与中文", "dual")
        self.language.addItem("只原文", "original")
        self.language.addItem("只中文", "zh")
        self.speaker = QCheckBox("SRT 包含人物名")
        self.speaker.setChecked(True)
        layout.addRow("格式", self.format)
        layout.addRow("范围", self.scope)
        layout.addRow(self.group)
        layout.addRow("字幕语言", self.language)
        layout.addRow(self.speaker)
        buttons = confirmation_buttons()
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)


class ProposalsDialog(QDialog):
    changed = Signal()

    def __init__(self, project, parent):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("识别与回导建议")
        self.resize(950, 640)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "人工版本保留在左侧。接受建议会记录历史，可撤销。机器建议重新审核；回导的人工审核状态保留。"
            )
        )
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["时间与版本", "当前人工版本", "新建议"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setWordWrap(True)
        layout.addWidget(self.table)
        actions = QHBoxLayout()
        actions.addWidget(button("接受选中建议", self.accept_selected))
        actions.addWidget(button("忽略选中建议", self.ignore_selected))
        layout.addLayout(actions)
        self.reload()

    def reload(self):
        self.items = self.project.proposals()
        self.table.setRowCount(len(self.items))
        for i, p in enumerate(self.items):
            current = self.project.get("utterances", p["row_id"])
            candidate = p["data"]
            conflict = current["revision"] != p["base_revision"]
            self.table.setItem(
                i,
                0,
                QTableWidgetItem(
                    stamp(current["start_ms"])
                    + ("\n原版本已变化，请检查冲突" if conflict else "\n可比较")
                ),
            )
            self.table.setItem(
                i,
                1,
                QTableWidgetItem(
                    current["original"]
                    + "\n"
                    + current["translation"]
                    + "\n"
                    + self.project.role(current)
                ),
            )
            self.table.setItem(
                i,
                2,
                QTableWidgetItem(
                    candidate.get("original", "（原文不变）")
                    + "\n"
                    + candidate.get("translation", "（中文不变）")
                    + "\n"
                    + self.project.role(candidate)
                ),
            )
        self.table.resizeRowsToContents()

    def accept_selected(self):
        i = self.table.currentRow()
        if i >= 0:
            self.project.accept_proposal(self.items[i]["id"])
            self.changed.emit()
            self.reload()

    def ignore_selected(self):
        i = self.table.currentRow()
        if i >= 0:
            with self.project.db:
                self.project.db.execute(
                    "UPDATE proposals SET status='ignored' WHERE id=?", (self.items[i]["id"],)
                )
            self.reload()
