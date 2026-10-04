"""Project actions and editing; widget layout and display live in workspace.py."""

import json
import sys
from pathlib import Path

from PySide6.QtCore import (
    QItemSelectionModel,
    QLockFile,
    QProcess,
    QSignalBlocker,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import QColor
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QTreeWidgetItem,
)

from . import __version__
from .dialogs import (
    EpisodeDialog,
    ExportDialog,
    ModelsDialog,
    ProposalsDialog,
    TurnsDialog,
    WorkThread,
)
from .domain import parse_stamp, stamp, utterance
from .exporters import export_docx, export_html, export_json, export_srt, export_txt
from .importers import import_transcript
from .media import probe
from .settings import save_settings, settings
from .store import Project
from .workspace import STYLE, WorkspaceMixin


class MainWindow(WorkspaceMixin, QMainWindow):
    def __init__(self, folder=None):
        super().__init__()
        self.project = None
        self.current_episode = None
        self.current_row = None
        self.loading = False
        self.editor_dirty = False
        self.person_dirty = False
        self.threads = []
        self.active_job = None
        self.closing = False
        self.project_lock = None
        self.playing_episode = None
        self.pending_seek = None
        self.resize(1480, 900)
        self.setMinimumSize(1060, 640)
        self.setWindowTitle("AnimeDialog " + __version__ + " · 视频台词整理与审核")
        self.setStyleSheet(STYLE)
        self.build_toolbar()
        self.build_layout()
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.worker_output)
        self.process.finished.connect(self.worker_finished)
        if not getattr(sys, "frozen", False):
            self.process.setWorkingDirectory(str(Path(__file__).resolve().parent.parent))
        self.job_timer = QTimer(self)
        self.job_timer.timeout.connect(self.refresh_jobs)
        self.job_timer.start(1000)
        self.filter_timer = QTimer(self)
        self.filter_timer.setSingleShot(True)
        self.filter_timer.timeout.connect(self.refresh_rows)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self.save_editor)
        self.player.errorOccurred.connect(self.player_error)
        self.player.tracksChanged.connect(self.select_audio_track)
        self.player.mediaStatusChanged.connect(self.media_status_changed)
        self.player.seekableChanged.connect(lambda _: self.apply_pending_seek())
        if folder:
            self.open_project(folder)
        else:
            recent = settings().get("last_project")
            if recent and (Path(recent) / "project.sqlite").exists():
                self.open_project(recent)
            else:
                self.statusBar().showMessage(
                    "创建作品项目，或打开之前的项目。首次识别前请安装本地模型。"
                )

    def require_project(self):
        if self.project:
            return True
        QMessageBox.information(self, "还没有作品", "请先新建作品或打开项目。")
        return False

    def warn(self, error):
        QMessageBox.warning(self, "操作未完成", str(error))

    def new_project(self):
        title, ok = QInputDialog.getText(self, "新建作品", "作品名称")
        if not ok or not title.strip():
            return
        parent = QFileDialog.getExistingDirectory(
            self, "选择保存作品的位置", str(Path.home() / "Documents")
        )
        if not parent:
            return
        safe = "".join("_" if c in '<>:"/\\|?*' else c for c in title).strip(". ")
        folder = Path(parent) / safe
        if (folder / "project.sqlite").exists():
            self.warn("该项目已存在，请打开它或使用不同名称。")
            return
        self.open_project(folder, title)

    def choose_project(self):
        folder = QFileDialog.getExistingDirectory(self, "打开作品项目文件夹")
        if folder:
            if not (Path(folder) / "project.sqlite").exists():
                self.warn("该文件夹不是 AnimeDialog 项目。")
                return
            self.open_project(folder)

    def open_project(self, folder, title=None):
        if self.active_job:
            self.warn("处理任务正在运行，请暂停并等待停止后再切换作品。")
            return
        if any(t.isRunning() for t in self.threads):
            self.warn("正在读取视频信息，请稍后再切换作品。")
            return
        try:
            folder = Path(folder).resolve()
            folder.mkdir(parents=True, exist_ok=True)
            if self.project and self.project.folder == folder:
                return
            lock = QLockFile(str(folder / ".animedialog.lock"))
            lock.setStaleLockTime(0)
            if not lock.tryLock(0):
                self.warn("此项目已在另一个窗口中打开，请先关闭那个窗口。")
                return
            if self.project:
                if not self.save_editor():
                    lock.unlock()
                    return
                self.player.stop()
                self.project.close()
                self.project_lock.unlock()
            self.project_lock = lock
            self.project = Project(folder, title)
            self.current_episode = None
            self.current_row = None
            self.playing_episode = None
            self.pending_seek = None
            self.player.setSource(QUrl())
            self.video_hint.setText("点击右侧台词定位视频")
            self.video_hint.setToolTip("")
            for job in self.project.all("jobs"):
                if job["state"] == "running":
                    self.project.update_job(
                        job["id"],
                        state="paused",
                        request="pause",
                        error="上次运行中断，可继续从检查点恢复",
                    )
            s = settings()
            s["last_project"] = str(self.project.folder)
            save_settings(s)
            self.heading.setText(self.project.meta("title"))
            self.setWindowTitle(self.project.meta("title") + " · AnimeDialog " + __version__)
            self.reset_transcript_filters()
            self.refresh_sidebar()
            self.refresh_rows()
            self.refresh_jobs()
            self.editor.setEnabled(False)
            self.update_commands()
        except Exception as e:
            self.warn(e)

    def add_videos(self):
        if not self.require_project():
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "添加动漫或电视剧视频",
            "",
            "视频 (*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.ts);;全部文件 (*)",
        )
        if not paths:
            return
        eps = []
        for p in paths:
            if not any(e["path"] == str(Path(p).resolve()) for e in self.project.episodes()):
                eps.append(self.project.add_episode(p))
        self.refresh_sidebar()
        self.worker_status.setText("正在检查视频轨道…")

        def work(t):
            return [(e["id"], probe(e["path"])) for e in eps]

        thread = WorkThread(work, self)
        self.threads.append(thread)

        def done(results):
            for id, meta in results:
                e = self.project.get("episodes", id)
                e["metadata"] = meta
                e["duration_ms"] = round(float(meta["format"].get("duration", 0)) * 1000)
                streams = [s for s in meta["streams"] if s["codec_type"] == "audio"]
                e["audio_index"] = streams[0]["index"] if streams else None
                self.project.put("episodes", e)
            self.worker_status.setText("视频已添加。可设置原声、音轨与中文字幕，再开始处理。")
            self.refresh_sidebar()

        thread.done.connect(done)
        thread.failed.connect(self.warn)
        thread.start()

    def refresh_sidebar(self):
        if not self.project:
            return
        old_char = (
            self.characters.currentItem().data(Qt.UserRole)
            if self.characters.currentItem()
            else None
        )
        self.episodes.blockSignals(True)
        self.characters.blockSignals(True)
        self.episodes.clear()
        all_item = QTreeWidgetItem(["全部剧集"])
        all_item.setData(0, Qt.UserRole, None)
        self.episodes.addTopLevelItem(all_item)
        for e in self.project.episodes():
            item = QTreeWidgetItem([f"{e['number']:02}  {e['title']}"])
            item.setData(0, Qt.UserRole, e["id"])
            self.episodes.addTopLevelItem(item)
            if e["id"] == self.current_episode:
                self.episodes.setCurrentItem(item)
        if self.current_episode is None:
            self.episodes.setCurrentItem(all_item)
        self.characters.clear()
        self.characters.addItem("全部人物")
        self.characters.item(0).setData(Qt.UserRole, None)
        for c in self.project.characters():
            self.characters.addItem(c["name"])
            item = self.characters.item(self.characters.count() - 1)
            item.setData(Qt.UserRole, c["id"])
            item.setToolTip(
                c["name"] + ("\n别名：" + ", ".join(c["aliases"]) if c.get("aliases") else "")
            )
            if c["id"] == old_char:
                self.characters.setCurrentItem(item)
        if self.characters.currentItem() is None:
            self.characters.setCurrentRow(0)
        self.episodes.blockSignals(False)
        self.characters.blockSignals(False)
        self.update_person_options()
        self.project_summary.setText(
            f"{len(self.project.episodes())} 集 · {len(self.project.characters())} 位人物"
        )

    def update_person_options(self):
        selected = self.person.currentData()
        self.person.blockSignals(True)
        self.person.clear()
        self.person.addItem("待确认 / 多人分句", None)
        for c in self.project.characters():
            self.person.addItem(c["name"], c["id"])
        self.person.setCurrentIndex(max(0, self.person.findData(selected)))
        self.person.blockSignals(False)

    def episode_selected(self):
        if not self.project:
            return
        if not self.save_editor():
            self.refresh_sidebar()
            return
        item = self.episodes.currentItem()
        self.current_episode = item.data(0, Qt.UserRole) if item else None
        if self.current_episode:
            self.load_video(self.current_episode)
        self.refresh_rows()

    def character_selected(self):
        self.refresh_rows()

    def move_episode(self, direction):
        if not self.project or not self.current_episode:
            return
        eps = self.project.episodes()
        i = next(i for i, e in enumerate(eps) if e["id"] == self.current_episode)
        j = i + direction
        if j < 0 or j >= len(eps):
            return
        eps[i]["number"], eps[j]["number"] = eps[j]["number"], eps[i]["number"]
        self.project.commit(
            "调整剧集顺序", [("episodes", eps[i], eps[i]["id"]), ("episodes", eps[j], eps[j]["id"])]
        )
        self.refresh_sidebar()
        self.refresh_rows()

    def relink(self):
        if not self.current_episode:
            self.warn("请先选择一集。")
            return
        p, _ = QFileDialog.getOpenFileName(
            self, "重新关联视频", "", "视频 (*.mp4 *.mkv *.mov *.avi *.webm);;全部文件 (*)"
        )
        if p:
            e = self.project.get("episodes", self.current_episode)
            e["path"] = str(Path(p).resolve())
            e.pop("preview_path", None)
            self.project.commit("重新关联视频", [("episodes", e, e["id"])])
            self.load_video(e["id"])

    def episode_settings(self):
        if not self.current_episode:
            self.warn("请先选择一集。")
            return
        e = self.project.get("episodes", self.current_episode)
        dialog = EpisodeDialog(e, self)
        if dialog.exec():
            e = dialog.episode
            e["options"] = dialog.options
            self.project.commit("剧集设置", [("episodes", e, e["id"])])
            self.refresh_sidebar()

    def load_video(self, episode_id):
        self.playing_episode = episode_id
        e = self.project.get("episodes", episode_id)
        p = e.get("preview_path") or e["path"]
        if p and Path(p).is_file():
            url = QUrl.fromLocalFile(p)
            self.video_hint.setText(
                e["title"] + " · " + ("兼容预览" if e.get("preview_path") else "原视频")
            )
            self.video_hint.setToolTip(p)
            if self.player.source() != url:
                self.player.setSource(url)
        else:
            self.player.stop()
            self.player.setSource(QUrl())
            self.pending_seek = None
            self.video_hint.setText("视频未关联或已移动 · 左侧“设置”可重新关联")
            self.video_hint.setToolTip(p or "")
        self.update_commands()

    def select_audio_track(self):
        if not self.project or not self.playing_episode:
            return
        e = self.project.get("episodes", self.playing_episode)
        streams = [
            s for s in e.get("metadata", {}).get("streams", []) if s.get("codec_type") == "audio"
        ]
        selected = next((i for i, s in enumerate(streams) if s["index"] == e.get("audio_index")), 0)
        if not e.get("preview_path") and selected < len(self.player.audioTracks()):
            self.player.setActiveAudioTrack(selected)

    def refresh_rows(self, *_):
        if not self.project:
            return
        if not self.save_editor():
            return
        selected = self.current_row["id"] if self.current_row else None
        selected_ids = set(self.selected_ids())
        character = self.chosen_character()
        rows = self.project.rows(
            self.current_episode,
            character,
            self.kind.currentData(),
            self.search.text(),
            self.review_filter.currentData(),
        )
        self.loading = True
        self.table_model.set_rows(rows, self.project.characters())
        selection = self.table.selectionModel()
        for i, r in enumerate(rows):
            if r["id"] in selected_ids:
                selection.select(
                    self.table_model.index(i, 0),
                    QItemSelectionModel.Select | QItemSelectionModel.Rows,
                )
        if selected:
            found = self.table_model.row_index(selected)
            if found >= 0:
                selection.setCurrentIndex(
                    self.table_model.index(found, 0), QItemSelectionModel.NoUpdate
                )
                if not selected_ids:
                    selection.select(
                        self.table_model.index(found, 0),
                        QItemSelectionModel.Select | QItemSelectionModel.Rows,
                    )
                self.current_row = self.project.get("utterances", selected)
            else:
                self.current_row = None
                self.editor.setEnabled(False)
        self.loading = False
        if self.current_row:
            self.load_editor()
        else:
            self.editor.setEnabled(False)
            self.editor.setToolTip("")
        episode = (
            self.project.get("episodes", self.current_episode) if self.current_episode else None
        )
        char = self.project.get("characters", character) if character else None
        self.scope_label.setText(
            (episode["title"] if episode else "全部剧集")
            + " · "
            + (char["name"] if char else "全部人物")
        )
        self.scope_label.setToolTip(self.scope_label.text())
        self.update_commands()

    def selected_ids(self):
        return [
            self.table_model.rows[i.row()]["id"] for i in self.table.selectionModel().selectedRows()
        ]

    def row_selected(self, *_):
        if self.loading:
            return
        self.update_commands()
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            return
        index = self.table.currentIndex().row()
        if index < 0:
            index = indexes[0].row()
        if not 0 <= index < len(self.table_model.rows):
            return
        target = self.table_model.rows[index]
        if self.current_row and self.current_row["id"] == target["id"]:
            return
        if not self.save_editor():
            self.loading = True
            if self.current_row:
                previous = self.table_model.row_index(self.current_row["id"])
                if previous >= 0:
                    self.table.selectRow(previous)
            self.loading = False
            self.update_commands()
            return
        self.current_row = self.project.get("utterances", target["id"])
        self.load_editor()
        self.load_video(target["episode_id"])
        self.seek_video(max(0, target["start_ms"] - 300))

    def load_editor(self):
        if not self.current_row:
            return
        r = self.current_row
        self.loading = True
        self.editor.setEnabled(True)
        self.start.setText(stamp(r["start_ms"]))
        self.end.setText(stamp(r["end_ms"]))
        self.original.setPlainText(r["original"])
        self.translation.setPlainText(r["translation"])
        self.notes.setText(r["notes"])
        self.person.setCurrentIndex(
            max(
                0,
                self.person.findData(
                    r["character_ids"][0]
                    if len(r["character_ids"]) == 1 and not r["turns"]
                    else None
                ),
            )
        )
        self.speaker_review.setChecked(r["speaker_review"] == "confirmed")
        self.text_review.setChecked(r["text_review"] == "confirmed")
        self.row_kind.setCurrentText(r["kind"])
        explanation = "；".join(r["evidence"] + r["flags"]) or "尚无可靠归属依据。"
        self.evidence.setText(explanation)
        self.evidence.setToolTip(explanation)
        episode = self.project.get("episodes", r["episode_id"])
        self.editor.setToolTip("记录编号：" + r["id"])
        self.editor.setTitle(
            "台词编辑 · "
            + (f"第 {episode['number']:02} 集 · " if episode else "")
            + stamp(r["start_ms"])[:-4]
        )
        self.loading = False
        self.editor_dirty = False
        self.person_dirty = False
        self.set_save_status()
        self.update_commands()

    def editor_changed(self, *_):
        if not self.loading and self.current_row:
            self.editor_dirty = True
            if self.sender() == self.person:
                self.person_dirty = True
            self.set_save_status("正在编辑…", "dirty")
            self.save_timer.start(650)

    def save_editor(self, *_):
        if not self.project or not self.current_row or self.loading:
            return True
        if not self.editor.isEnabled():
            return True
        if not self.editor_dirty:
            return True
        self.save_timer.stop()
        try:
            r = self.project.get("utterances", self.current_row["id"])
            cid = self.person.currentData()
            fields = dict(
                start_ms=parse_stamp(self.start.text()),
                end_ms=parse_stamp(self.end.text()),
                original=self.original.toPlainText(),
                translation=self.translation.toPlainText(),
                notes=self.notes.text(),
                kind=self.row_kind.currentText(),
                text_review="confirmed" if self.text_review.isChecked() else "pending",
                speaker_review="confirmed" if self.speaker_review.isChecked() else "pending",
            )
            if self.person_dirty:
                fields.update(
                    character_ids=[cid] if cid else [], turns=[], evidence=["人工调整人物归属"]
                )
            if fields["speaker_review"] == "confirmed" and not (
                cid
                or r["turns"]
                and all(
                    t.get("character_id") and t.get("review") == "confirmed" for t in r["turns"]
                )
            ):
                fields["speaker_review"] = "pending"
            if any(r.get(k) != v for k, v in fields.items()):
                self.project.edit(r["id"], **fields)
                self.current_row = self.project.get("utterances", r["id"])
                index = self.table_model.row_index(r["id"])
                if index >= 0:
                    self.table_model.rows[index] = self.current_row
                    self.table_model.dataChanged.emit(
                        self.table_model.index(index, 0), self.table_model.index(index, 5)
                    )
                self.statusBar().showMessage("修改已自动保存", 3000)
            self.editor_dirty = False
            self.person_dirty = False
            self.loading = True
            self.speaker_review.setChecked(self.current_row["speaker_review"] == "confirmed")
            self.text_review.setChecked(self.current_row["text_review"] == "confirmed")
            self.loading = False
            self.set_save_status()
            return True
        except Exception as e:
            self.set_save_status("未保存，请检查输入", "error")
            self.save_status.setToolTip(str(e))
            self.statusBar().showMessage("尚未保存：" + str(e))
            return False

    def add_character(self):
        if not self.require_project():
            return
        if not self.save_editor():
            return
        name, ok = QInputDialog.getText(self, "增加作品人物", "姓名（声音不确定时可用临时名称）")
        if not ok or not name.strip():
            return
        cid = self.project.character(name.strip())
        self.edit_character_details(cid)
        self.refresh_sidebar()

    def edit_character_details(self, cid):
        c = self.project.get("characters", cid)
        aliases, ok = QInputDialog.getText(
            self, "人物别名", "别名用逗号分隔，可留空", text=",".join(c["aliases"])
        )
        if ok:
            c["aliases"] = [a.strip() for a in aliases.replace("，", ",").split(",") if a.strip()]
            self.project.commit("编辑人物别名", [("characters", c, cid)])

    def chosen_character(self):
        return (
            self.characters.currentItem().data(Qt.UserRole)
            if self.characters.currentItem()
            else None
        )

    def rename_character(self):
        if not self.save_editor():
            return
        cid = self.chosen_character()
        if not cid:
            self.warn("请先选择一个人物。")
            return
        c = self.project.get("characters", cid)
        name, ok = QInputDialog.getText(
            self, "重命名人物", "修改姓名后应用于全部剧集", text=c["name"]
        )
        if ok and name.strip():
            if any(x["id"] != cid and x["name"] == name.strip() for x in self.project.characters()):
                self.warn("同名人物已存在，可使用合并人物。")
                return
            c["aliases"] = list(dict.fromkeys(c["aliases"] + [c["name"]]))
            c["name"] = name.strip()
            self.project.commit("重命名人物", [("characters", c, cid)])
            self.refresh_sidebar()
            self.refresh_rows()

    def merge_character(self):
        if not self.save_editor():
            return
        source = self.chosen_character()
        if not source:
            self.warn("请先选择要合并的人物。")
            return
        candidates = [c for c in self.project.characters() if c["id"] != source]
        name, ok = QInputDialog.getItem(
            self,
            "合并人物",
            "将选中人物的台词和声音样本合并到：",
            [c["name"] for c in candidates],
            editable=False,
        )
        if ok:
            self.project.merge_characters(
                source, next(c["id"] for c in candidates if c["name"] == name)
            )
            self.refresh_sidebar()
            self.refresh_rows()

    def assign_selected(self):
        if not self.save_editor():
            return
        ids = self.selected_ids()
        if not ids:
            return
        candidates = self.project.characters()
        labels = ["新建人物并归类"] + [c["name"] for c in candidates]
        name, ok = QInputDialog.getItem(
            self, "批量归类", f"为 {len(ids)} 条台词选择已核对的人物", labels, editable=False
        )
        if not ok:
            return
        if name == labels[0]:
            name, ok = QInputDialog.getText(self, "新建人物", "人物名称")
            if not ok or not name.strip():
                return
            cid = self.project.character(name.strip())
        else:
            cid = next(c["id"] for c in candidates if c["name"] == name)
        self.project.assign(ids, cid)
        self.current_row = None
        self.editor.setEnabled(False)
        self.refresh_sidebar()
        self.refresh_rows()

    def turns(self):
        if not self.current_row:
            return
        if not self.save_editor():
            return
        r = self.project.get("utterances", self.current_row["id"])
        dialog = TurnsDialog(r, self.project.characters(), self)
        if dialog.exec():
            turns = dialog.row["turns"]
            ids = list(dict.fromkeys(t["character_id"] for t in turns if t.get("character_id")))
            text = "\n".join(t["text"] for t in turns)
            self.project.edit(
                r["id"],
                turns=turns,
                translation=text,
                character_ids=ids,
                text_review=r["text_review"] if text == r["translation"] else "pending",
                speaker_review="confirmed"
                if turns
                and all(t.get("character_id") and t["review"] == "confirmed" for t in turns)
                else "pending",
                evidence=r["evidence"] + ["人工分句核对；未填写时间的分句仍使用整段定位时间"],
            )
            self.current_row = self.project.get("utterances", r["id"])
            self.load_editor()
            self.refresh_rows()

    def add_row(self):
        episode_id = self.current_episode or self.playing_episode
        if not episode_id:
            self.warn("请选择一集后新增台词。")
            return
        if not self.save_editor():
            return
        r = utterance(
            episode_id, self.player.position(), self.player.position() + 3000, source="manual"
        )
        self.project.commit("新增台词", [("utterances", r, r["id"])])
        self.current_row = None
        self.refresh_rows()
        if (
            self.kind.currentData()
            or self.review_filter.currentData()
            or self.search.text()
            or self.chosen_character()
        ):
            self.reset_transcript_filters()
            with QSignalBlocker(self.characters):
                self.characters.setCurrentRow(0)
            self.refresh_rows()
        self.select_record(r["id"])

    def delete_rows(self):
        if not self.save_editor():
            return
        changes = []
        for id in self.selected_ids():
            r = self.project.get("utterances", id)
            r["deleted"] = True
            changes.append(("utterances", r, id))
        if changes:
            self.project.commit("删除台词（可撤销）", changes)
            self.current_row = None
            self.editor.setEnabled(False)
            self.refresh_rows()

    def split_row(self):
        if not self.current_row:
            return
        if not self.save_editor():
            return
        r = self.current_row
        text, ok = QInputDialog.getText(
            self,
            "拆分台词",
            "拆分时间，须回看确认：",
            text=stamp(
                self.player.position()
                if r["start_ms"] < self.player.position() < r["end_ms"]
                else (r["start_ms"] + r["end_ms"]) // 2
            ),
        )
        if not ok:
            return
        parts = []
        for label, value in [("原文", r["original"]), ("中文", r["translation"])]:
            left, ok = QInputDialog.getMultiLineText(
                self, "拆分" + label, "第一句文字（第二句会保留剩余内容，可随后修改）", value
            )
            if not ok:
                return
            if left and not value.startswith(left):
                self.warn("第一句文字应为原文本的前半部分；需要改字时请先编辑台词。")
                return
            parts.append((left, value[len(left) :]))
        try:
            self.project.split(r["id"], parse_stamp(text), parts[0], parts[1])
            self.current_row = None
            self.refresh_rows()
        except Exception as e:
            self.warn(e)

    def merge_rows(self):
        if not self.save_editor():
            return
        try:
            self.project.merge_rows(self.selected_ids())
            self.current_row = None
            self.refresh_rows()
        except Exception as e:
            self.warn(e)

    def history(self, redo):
        if not self.project:
            return
        if not self.save_editor():
            return
        id = self.current_row["id"] if self.current_row else None
        if self.project.history_step(redo):
            self.current_row = self.project.get("utterances", id) if id else None
            if self.current_row and self.current_row.get("deleted"):
                self.current_row = None
            self.refresh_sidebar()
            self.refresh_rows()
            self.load_editor()
        self.statusBar().showMessage("已重做" if redo else "已撤销", 2500)

    def import_file(self):
        if not self.require_project():
            return
        if not self.save_editor():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "导入之前整理的台词或 HTML 人工核对结果", "", "台词文件 (*.json *.html *.htm)"
        )
        if path:
            try:
                inserted, conflicts = import_transcript(self.project, path, self.current_episode)
                self.refresh_sidebar()
                self.refresh_rows()
                self.statusBar().showMessage(
                    f"导入 {inserted} 条；{conflicts} 条变化可在“识别与回导建议”中比较。", 10000
                )
            except Exception as e:
                self.warn(e)

    def export(self):
        if not self.require_project():
            return
        if not self.save_editor():
            return
        dialog = ExportDialog(self)
        if not dialog.exec():
            return
        scope = dialog.scope.currentIndex()
        rows = (
            self.table_model.rows
            if scope == 0
            else self.project.rows()
            if scope == 1
            else self.project.rows(self.current_episode)
        )
        if not rows:
            self.warn("当前范围没有可导出的台词。")
            return
        ext = ["docx", "html", "txt", "srt", "json"][dialog.format.currentIndex()]
        name = self.project.meta("title") + "台词本." + ext
        path, _ = QFileDialog.getSaveFileName(
            self, "保存台词本", str(self.project.folder / name), f"{ext.upper()} (*.{ext})"
        )
        if not path:
            return
        if not Path(path).suffix:
            path += "." + ext
        try:
            grouped = dialog.group.isChecked()
            character = self.chosen_character() if scope == 0 else None
            if ext == "docx":
                export_docx(self.project, rows, path, grouped, character)
            elif ext == "html":
                export_html(self.project, rows, path, grouped)
            elif ext == "txt":
                export_txt(self.project, rows, path, grouped, character)
            elif ext == "json":
                export_json(self.project, rows, path)
            elif ext == "srt":
                export_srt(
                    self.project,
                    rows,
                    path,
                    dialog.language.currentData(),
                    dialog.speaker.isChecked(),
                )
            self.statusBar().showMessage("已导出：" + path, 12000)
        except Exception as e:
            self.warn(e)

    def models(self):
        ModelsDialog(self).exec()

    def review_statistics(self):
        if not self.require_project() or not self.save_editor():
            return

        from .statistics import review_statistics

        stats = review_statistics(self.project)
        path = self.project.folder / "审核统计.json"
        path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf8")
        text_rate = stats["original_character_difference_rate"]
        speaker_rate = stats["speaker_disagreement_rate"]
        message = f"共 {stats['records']} 条台词\n人物人工确认 {stats['human_speaker_confirmed']} 条，待复核 {stats['speaker_pending']} 条\n文字已校对 {stats['human_text_confirmed']} 条，待校对 {stats['text_pending']} 条\n"
        message += (
            "原文字符差异："
            + (
                f"{text_rate:.2%}（{stats['original_reference_rows']} 条人工参考）"
                if text_rate is not None
                else "尚无人工参考，无法计算"
            )
            + "\n"
        )
        message += (
            "人物候选差异："
            + (
                f"{speaker_rate:.2%}（{stats['speaker_reference_rows']} 条人工参考）"
                if speaker_rate is not None
                else "尚无人工参考，无法计算"
            )
            + "\n\n统计只覆盖已经人工核对的记录。\n已保存："
            + str(path)
        )
        QMessageBox.information(self, "审核统计", message)

    def proposals(self):
        if not self.require_project():
            return
        if not self.save_editor():
            return
        dialog = ProposalsDialog(self.project, self)
        dialog.changed.connect(lambda: (self.refresh_sidebar(), self.refresh_rows()))
        dialog.exec()
        if self.current_row:
            self.current_row = self.project.get("utterances", self.current_row["id"])
            self.load_editor()

    def queue_all(self):
        if not self.require_project():
            return
        if not self.save_editor():
            return
        eps = (
            [self.project.get("episodes", self.current_episode)]
            if self.current_episode
            else self.project.episodes()
        )
        if not eps:
            self.warn("请先添加视频。")
            return
        for e in eps:
            if not e["path"] or not Path(e["path"]).is_file():
                self.warn(e["title"] + "没有关联视频，请重新关联后再处理。")
                return
        for e in eps:
            self.project.new_job(
                e["id"],
                e.get("options", dict(speakers=True, semantic=True, ocr=bool(e["ocr_regions"]))),
            )
        self.refresh_jobs()
        self.start_next_job()

    def task(self, task, **options):
        if not self.project or not self.save_editor():
            return
        if not self.current_row and not self.current_episode:
            self.warn("请选择一集或一条台词。")
            return
        episode_id = self.current_row["episode_id"] if self.current_row else self.current_episode
        self.project.new_job(episode_id, dict(task=task, **options))
        self.refresh_jobs()
        self.start_next_job()

    def preview_video(self):
        self.task("preview")

    def voice_sample(self):
        if self.current_row and self.save_editor():
            self.task("sample", row_id=self.current_row["id"])

    def match_voices(self):
        self.task("match")

    def retranscribe(self):
        if self.current_row and self.save_editor():
            self.task(
                "transcribe",
                target_ids=[self.current_row["id"]],
                large=True,
                speakers=False,
                semantic=False,
            )

    def start_next_job(self):
        if self.active_job or not self.project:
            return
        queued = [
            j
            for j in self.project.all("jobs")
            if j["state"] == "queued" and j.get("request") == "run"
        ]
        if not queued:
            return
        job = queued[0]
        self.project.update_job(job["id"], state="running", error="")
        self.active_job = job["id"]
        args = (
            ["--worker", "--project", str(self.project.folder), "--job", job["id"]]
            if getattr(sys, "frozen", False)
            else [
                "-m",
                "animedialog.worker",
                "--project",
                str(self.project.folder),
                "--job",
                job["id"],
            ]
        )
        self.process.start(sys.executable, args)
        if not self.process.waitForStarted(8000):
            self.project.update_job(
                job["id"], state="failed", error="处理进程无法启动：" + self.process.errorString()
            )
            self.active_job = None

    def worker_output(self):
        text = bytes(self.process.readAllStandardOutput()).decode("utf8", errors="replace")
        for line in text.splitlines():
            try:
                item = json.loads(line)
                if item.get("type") == "progress":
                    self.worker_status.setText(
                        item.get("stage", "") + " · " + item.get("message", "")
                    )
                elif item.get("type") == "error":
                    self.worker_status.setText(item.get("message", ""))
            except ValueError:
                pass

    def worker_finished(self, *_):
        preview_episode = None
        if self.project and self.active_job:
            job = self.project.get("jobs", self.active_job)
            if job["state"] == "completed" and job["options"].get("task") == "preview":
                preview_episode = job["episode_id"]
            if job["state"] == "running":
                self.project.update_job(
                    job["id"],
                    state="paused" if job.get("request") == "pause" else "failed",
                    error="处理进程已停止，可继续从检查点恢复",
                )
        self.active_job = None
        if self.project:
            self.refresh_sidebar()
            self.refresh_rows()
            self.refresh_jobs()
        if preview_episode and not self.closing:
            position = self.player.position()
            self.load_video(preview_episode)
            self.seek_video(position)
        if not self.closing:
            self.start_next_job()

    def refresh_jobs(self):
        if not self.project:
            return
        selected = self.jobs.currentItem().data(Qt.UserRole) if self.jobs.currentItem() else None
        scroll = self.jobs.verticalScrollBar().value()
        self.jobs.blockSignals(True)
        eps = {e["id"]: e["title"] for e in self.project.episodes()}
        states = dict(
            queued="排队",
            running="处理中",
            completed="完成",
            paused="暂停",
            cancelled="取消",
            failed="失败",
        )
        jobs = self.project.all("jobs")
        while self.jobs.count() > len(jobs):
            self.jobs.takeItem(self.jobs.count() - 1)
        for n, j in enumerate(jobs):
            if j["id"] == self.active_job:
                self.worker_status.setText(j.get("stage", "") + " · " + j.get("message", ""))
            if n >= self.jobs.count():
                self.jobs.addItem("")
            item = self.jobs.item(n)
            item.setText(
                f"{eps.get(j['episode_id'], '')} · {states.get(j['state'], j['state'])}\n{j.get('stage', '')} {j.get('progress', 0):.0f}% {j.get('error', '')[:60]}"
            )
            item.setData(Qt.UserRole, j["id"])
            item.setToolTip(j.get("error", "") or j.get("message", ""))
            item.setForeground(
                QColor(
                    "#b74e4e"
                    if j["state"] == "failed"
                    else "#40836e"
                    if j["state"] == "completed"
                    else "#33475f"
                )
            )
            if j["id"] == selected:
                self.jobs.setCurrentItem(item)
        self.jobs.verticalScrollBar().setValue(scroll)
        self.jobs.blockSignals(False)
        self.update_job_controls()

    def selected_job(self):
        return (
            self.jobs.currentItem().data(Qt.UserRole)
            if self.jobs.currentItem()
            else self.active_job
        )

    def job_request(self, request):
        if not self.project:
            return
        id = self.selected_job()
        if not id:
            return
        j = self.project.get("jobs", id)
        if j["state"] == "completed":
            return
        fields = dict(request=request)
        if j["state"] != "running":
            fields["state"] = "paused" if request == "pause" else "cancelled"
        self.project.update_job(id, **fields)
        self.refresh_jobs()

    def resume_job(self):
        if not self.project:
            return
        id = self.selected_job()
        if not id:
            return
        j = self.project.get("jobs", id)
        if j["state"] in ["running", "completed"]:
            return
        self.project.update_job(id, state="queued", request="run", error="")
        self.refresh_jobs()
        self.start_next_job()

    def play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def position_changed(self, ms):
        if not self.seek.isSliderDown():
            self.seek.setValue(ms)
        self.clock.setText(stamp(ms)[:-4] + " / " + stamp(self.player.duration())[:-4])
        if (
            self.loop.isChecked()
            and self.current_row
            and self.current_row["episode_id"] == self.playing_episode
            and ms >= self.current_row["end_ms"]
        ):
            self.player.setPosition(self.current_row["start_ms"])
        for index, r in enumerate(self.table_model.rows):
            if r["episode_id"] == self.playing_episode and r["start_ms"] <= ms < r["end_ms"]:
                changed = self.table_model.playing_id != r["id"]
                self.table_model.playing(r["id"])
                focus = QApplication.focusWidget()
                editing = focus and (focus == self.editor or self.editor.isAncestorOf(focus))
                if (
                    changed
                    and self.follow.isChecked()
                    and not editing
                    and not self.editor_dirty
                    and len(self.selected_ids()) <= 1
                ):
                    self.table.scrollTo(
                        self.table_model.index(index, 0), QAbstractItemView.EnsureVisible
                    )
                return
        self.table_model.playing(None)

    def seek_video(self, ms):
        self.pending_seek = ms
        self.apply_pending_seek()
        self.player.play()

    def apply_pending_seek(self):
        if (
            self.pending_seek is not None
            and self.player.duration() > 0
            and self.player.isSeekable()
            and self.player.mediaStatus() in [QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia]
        ):
            ms = self.pending_seek
            self.pending_seek = None
            self.player.setPosition(ms)

    def media_status_changed(self, status):
        if status in [QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia]:
            self.apply_pending_seek()

    def duration_changed(self, duration):
        self.seek.setRange(0, duration)
        self.apply_pending_seek()

    def navigate(self, direction):
        if not self.table_model.rows:
            return
        if not self.save_editor():
            return
        i = self.table_model.row_index((self.current_row or {}).get("id"))
        i = max(0, min(len(self.table_model.rows) - 1, i + direction))
        self.select_record(self.table_model.rows[i]["id"])

    def player_error(self, *_):
        self.worker_status.setText(
            "视频播放失败：" + self.player.errorString() + "；可点击“生成兼容视频预览”。"
        )

    def help(self):
        from PySide6.QtGui import QDesktopServices

        from .settings import resource_root

        guide = resource_root() / "使用说明.html"
        if guide.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(guide)))
            return
        QMessageBox.information(
            self,
            "使用说明",
            "1. 新建作品，添加一个或多集视频。\n2. 在“模型与工具”下载或导入模型。\n3. 设置音轨、语言及字幕，开始本地处理。\n4. 点击台词回看，修改文字、人物和时间；人物与文字分别审核。\n5. 确认样本后可以推荐同作品其他台词的归属。\n6. 导出 Word、HTML、TXT 或 SRT。HTML 人工修改后保存副本，可重新导入软件比较。\n\n项目自动保存。删除、拆分、合并、归类可撤销。原视频仍由本机原路径读取。",
        )

    def closeEvent(self, event):
        if any(t.isRunning() for t in self.threads):
            self.statusBar().showMessage("正在读取视频信息，请稍后关闭。")
            event.ignore()
            return
        if not self.save_editor():
            event.ignore()
            return
        self.closing = True
        if self.active_job:
            self.project.update_job(self.active_job, request="pause")
            if not self.process.waitForFinished(8000):
                self.process.kill()
                self.process.waitForFinished(3000)
        self.player.stop()
        self.save_workspace()
        if self.project:
            self.project.close()
            self.project = None
        if self.project_lock:
            self.project_lock.unlock()
        super().closeEvent(event)
