"""Exercise shortcuts with real Qt key events in the application's own widgets."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from animedialog.domain import utterance
from animedialog.settings import settings
from animedialog.store import Project
from animedialog.ui import MainWindow


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("ANIMEDIALOG_HOME", str(tmp_path / "settings"))
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    if not QFontDatabase.families():
        from pathlib import Path

        for filename in ["msyh.ttc", "segoeui.ttf"]:
            QFontDatabase.addApplicationFont(str(Path(os.environ["WINDIR"]) / "Fonts" / filename))
    project = Project(tmp_path / "作品")
    ep = project.add_episode(tmp_path / "不存在的视频.mp4")
    cid = project.character("甲")
    rows = [
        utterance(
            ep["id"],
            i * 3000,
            i * 3000 + 2000,
            original=f"原文{i}",
            translation=f"中文{i}",
            character_ids=[cid],
        )
        for i in range(5)
    ]
    rows[1].update(speaker_review="confirmed", text_review="confirmed")
    rows[2].update(kind="画面文字", character_ids=[], text_review="confirmed")
    rows[3]["kind"] = "歌词"
    for row in rows:
        project.put("utterances", row)
    project.close()
    w = MainWindow(tmp_path / "作品")
    w.show()
    w.activateWindow()
    app.processEvents()
    w.select_record(rows[0]["id"])
    app.processEvents()
    yield w, rows, cid
    # Allow the invalid-time tests to close without losing their deliberately bad input.
    if w.current_row:
        w.load_editor()
    w.close()
    app.processEvents()


def test_global_review_shortcuts_keep_states_independent(workspace):
    w, rows, cid = workspace
    w.table.setFocus()
    QTest.keyClick(w.table, Qt.Key_F7)
    saved = w.project.get("utterances", rows[0]["id"])
    assert saved["speaker_review"] == "confirmed" and saved["text_review"] == "pending"
    QTest.keyClick(w.table, Qt.Key_F8)
    assert w.project.get("utterances", rows[0]["id"])["text_review"] == "confirmed"


def test_space_and_undo_in_text_do_not_trigger_playback_or_project_undo(workspace):
    w, rows, cid = workspace
    w.project.edit(rows[4]["id"], notes="之前保存的项目操作")
    plays = []
    for shortcut in w.widget_shortcuts:
        if shortcut.key().toString() == "Space":
            shortcut.activated.disconnect()
            shortcut.activated.connect(lambda: plays.append(True))
    w.original.setFocus()
    w.original.moveCursor(w.original.textCursor().MoveOperation.End)
    QTest.keyClick(w.original, Qt.Key_Space)
    assert w.original.toPlainText() == "原文0 " and not plays
    QTest.keyClick(w.original, Qt.Key_Z, Qt.ControlModifier)
    assert w.original.toPlainText() == "原文0"
    assert w.project.get("utterances", rows[4]["id"])["notes"] == "之前保存的项目操作"
    w.table.setFocus()
    QTest.keyClick(w.table, Qt.Key_Space)
    assert plays == [True]


@pytest.mark.parametrize("key", [Qt.Key_Return, Qt.Key_Enter])
def test_ctrl_enter_saves_text_review_and_moves_without_confirming_person(workspace, key):
    w, rows, cid = workspace
    w.translation.setFocus()
    QTest.keyClick(w.translation, key, Qt.ControlModifier)
    assert w.current_row["id"] == rows[1]["id"]
    saved = w.project.get("utterances", rows[0]["id"])
    assert saved["text_review"] == "confirmed" and saved["speaker_review"] == "pending"


def test_invalid_time_blocks_shortcuts_selection_and_history(workspace):
    w, rows, cid = workspace
    w.end.setText("00:00:00.000")
    w.editor_changed()
    w.table.setFocus()
    QTest.keyClick(w.table, Qt.Key_Down, Qt.AltModifier)
    assert w.current_row["id"] == rows[0]["id"]
    w.table.selectRow(1)
    assert w.current_row["id"] == rows[0]["id"] and w.table.currentIndex().row() == 0
    w.history(False)
    assert w.end.text() == "00:00:00.000" and w.save_status.property("state") == "error"
    assert w.project.get("utterances", rows[0]["id"])["end_ms"] == 2000


def test_refresh_preserves_batch_selection_and_dirty_edit(workspace):
    w, rows, cid = workspace
    selection = w.table.selectionModel()
    selection.select(
        w.table_model.index(1, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows
    )
    w.notes.setText("需要保留的备注")
    w.editor_changed()
    w.refresh_rows()
    assert set(w.selected_ids()) == {rows[0]["id"], rows[1]["id"]}
    assert w.project.get("utterances", rows[0]["id"])["notes"] == "需要保留的备注"
    assert w.commands["merge"].isEnabled() and "已选 2 条" in w.row_count.text()


def test_next_pending_skips_completed_screen_text_and_wraps(workspace):
    w, rows, cid = workspace
    w.next_pending()
    assert w.current_row["id"] == rows[3]["id"]
    w.select_record(rows[4]["id"])
    w.next_pending()
    assert w.current_row["id"] == rows[0]["id"]
    w.review_filter.setCurrentIndex(w.review_filter.findData("speaker"))
    assert rows[3]["id"] in {r["id"] for r in w.table_model.rows}
    assert rows[2]["id"] not in {r["id"] for r in w.table_model.rows}


def test_review_next_reapplies_pending_filter_without_losing_next_sentence(workspace):
    w, rows, cid = workspace
    w.review_filter.setCurrentIndex(w.review_filter.findData("text"))
    w.review_and_next()
    assert w.current_row["id"] == rows[3]["id"]
    assert rows[0]["id"] not in {r["id"] for r in w.table_model.rows}


def test_search_escape_and_editor_focus_shortcuts(workspace):
    w, rows, cid = workspace
    w.table.setFocus()
    QTest.keyClick(w.table, Qt.Key_F, Qt.ControlModifier)
    assert w.search.hasFocus()
    QTest.keyClicks(w.search, "notfound")
    QTest.keyClick(w.search, Qt.Key_Escape)
    assert w.search.text() == "" and w.table.hasFocus()
    QTest.keyClick(w.table, Qt.Key_3, Qt.ControlModifier)
    assert w.translation.hasFocus()
    w.resize(1280, 720)
    QApplication.processEvents()
    QTest.keyClick(w.translation, Qt.Key_2, Qt.ControlModifier)
    QApplication.processEvents()
    viewport_position = w.original.mapTo(w.editor_scroll.viewport(), w.original.rect().topLeft())
    assert viewport_position.y() >= 0
    assert viewport_position.y() + w.original.height() <= w.editor_scroll.viewport().height()


def test_new_sentence_is_visible_when_person_filter_is_active(workspace):
    w, rows, cid = workspace
    w.characters.setCurrentRow(1)
    w.add_row()
    assert w.current_row and w.current_row["source"] == "manual"
    assert w.current_row["character_ids"] == [] and w.chosen_character() is None


def test_first_sentence_all_episode_view_enables_adding_missing_lines(workspace):
    w, rows, cid = workspace
    assert w.current_episode is None and w.playing_episode == rows[0]["episode_id"]
    assert w.commands["add_row"].isEnabled()


def test_invalid_times_do_not_launch_processing_tasks(workspace):
    w, rows, cid = workspace
    w.end.setText("00:00:00.000")
    w.editor_changed()
    w.queue_all()
    w.preview_video()
    w.voice_sample()
    w.retranscribe()
    assert not w.project.all("jobs") and w.active_job is None


def test_layout_persists_and_reset_is_available_at_small_size(workspace):
    w, rows, cid = workspace
    w.resize(1280, 720)
    QApplication.processEvents()
    w.review_splitter.setSizes([160, 380])
    w.follow.setChecked(False)
    w.volume.setValue(35)
    w.save_workspace()
    state = settings()["workspace"]
    assert (
        state["review"] and state["geometry"] and state["volume"] == 35 and state["follow"] is False
    )
    w.volume.setValue(80)
    w.follow.setChecked(True)
    w.restore_workspace()
    assert w.volume.value() == 35 and w.follow.isChecked() is False
    assert w.width() <= 1280 and w.height() <= 720
    assert w.review_splitter.sizes()[1] >= 100
    w.commands["reset_layout"].trigger()
    assert all(size > 0 for size in w.splitter.sizes())


def test_fast_playback_and_aspect_selection_persist(workspace):
    w, rows, cid = workspace
    for rate in (3, 5):
        w.speed.setCurrentIndex(w.speed.findData(rate))
        assert w.player.playbackRate() == rate
    w.aspect.setCurrentText("4:3")
    w.save_workspace()
    state = settings()["workspace"]
    assert state["speed"] == 5 and state["aspect_ratio"] == 4 / 3
    w.speed.setCurrentIndex(w.speed.findData(1))
    w.aspect.setCurrentText("原始比例")
    w.restore_workspace()
    assert w.player.playbackRate() == 5 and w.aspect.currentData() == 4 / 3
    assert w.video.aspectRatioMode() == Qt.IgnoreAspectRatio


def test_video_aspect_fits_and_centers_when_resizing(workspace):
    w, rows, cid = workspace
    for size in ((1480, 900), (1280, 720), (1100, 680)):
        w.resize(*size)
        QApplication.processEvents()
        for label in ("原始比例", "16:9", "4:3", "1:1", "21:9", "铺满"):
            w.aspect.setCurrentText(label)
            QApplication.processEvents()
            frame, video = w.video_frame.rect(), w.video.geometry()
            assert frame.contains(video)
            assert abs(frame.center().x() - video.center().x()) <= 1
            assert abs(frame.center().y() - video.center().y()) <= 1
            ratio = w.aspect.currentData()
            if ratio:
                assert abs(video.width() - video.height() * ratio) <= max(1, ratio)
            else:
                assert video == frame
            expected_mode = Qt.KeepAspectRatio if ratio is None else Qt.IgnoreAspectRatio
            assert w.video.aspectRatioMode() == expected_mode


def test_refresh_jobs_does_not_reset_selection_or_allow_completed_restart(workspace):
    w, rows, cid = workspace
    first = w.project.new_job(rows[0]["episode_id"], {})
    w.project.new_job(rows[0]["episode_id"], {})
    w.project.update_job(first["id"], state="completed", progress=100)
    w.refresh_jobs()
    w.jobs.setCurrentRow(0)
    current = w.jobs.currentItem()
    w.refresh_jobs()
    assert w.jobs.currentItem() is current and w.selected_job() == first["id"]
    assert not w.job_buttons["resume"].isEnabled()
    w.resume_job()
    assert w.project.get("jobs", first["id"])["state"] == "completed"


def test_multi_person_cannot_be_confirmed_by_single_shortcut(workspace):
    w, rows, cid = workspace
    second = w.project.character("乙")
    w.project.edit(rows[0]["id"], character_ids=[cid, second])
    w.current_row = w.project.get("utterances", rows[0]["id"])
    w.refresh_sidebar()
    w.load_editor()
    w.confirm_speaker()
    assert w.current_row["speaker_review"] == "pending" and not w.speaker_review.isChecked()


def test_review_rules_agree_between_filters_navigation_and_colors(workspace):
    w, rows, cid = workspace
    w.project.edit(rows[4]["id"], speaker_review="confirmed")
    w.refresh_rows()
    for index, row in enumerate(w.table_model.rows):
        expected_color = "#39816a" if row["id"] in {rows[1]["id"], rows[2]["id"]} else "#8a6a38"
        assert (
            w.table_model.data(w.table_model.index(index, 5), Qt.ForegroundRole).name()
            == expected_color
        )

    pending_ids = {
        "speaker": {rows[0]["id"], rows[3]["id"]},
        "text": {rows[0]["id"], rows[3]["id"], rows[4]["id"]},
        "any": {rows[0]["id"], rows[3]["id"], rows[4]["id"]},
    }
    for mode in (None, "speaker", "text", "any"):
        w.review_filter.setCurrentIndex(w.review_filter.findData(mode))
        expected = pending_ids[mode] if mode else {row["id"] for row in rows}
        assert {row["id"] for row in w.table_model.rows} == expected
        for row in w.project.rows():
            assert w.is_pending(row) == (row["id"] in pending_ids[mode or "any"])

    # Screen text needs text review, but never needs a speaker assignment.
    w.project.edit(rows[2]["id"], text_review="pending")
    w.review_filter.setCurrentIndex(w.review_filter.findData("text"))
    assert rows[2]["id"] in {row["id"] for row in w.table_model.rows}
    w.review_filter.setCurrentIndex(w.review_filter.findData("speaker"))
    assert rows[2]["id"] not in {row["id"] for row in w.table_model.rows}
