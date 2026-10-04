"""Offscreen widget regression tests; actual Windows interaction is checked separately."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication

from animedialog.domain import utterance
from animedialog.store import Project
from animedialog.ui import MainWindow


@pytest.fixture
def window(tmp_path, monkeypatch):
    monkeypatch.setenv("ANIMEDIALOG_HOME", str(tmp_path / "settings"))
    _app = QApplication.instance() or QApplication([])
    p = Project(tmp_path / "作品")
    ep = p.add_episode(tmp_path / "video.mp4")
    a = p.character("甲")
    b = p.character("乙")
    r = utterance(
        ep["id"], 1000, 3000, original="人工原文", translation="人工中文", character_ids=[a, b]
    )
    p.put("utterances", r)
    p.close()
    w = MainWindow(tmp_path / "作品")
    w.current_row = w.project.get("utterances", r["id"])
    w.load_editor()
    yield w, r, a, b
    w.close()


def test_edit_notes_does_not_erase_multi_person_candidates(window):
    w, r, a, b = window
    w.notes.setText("新增备注")
    w.editor_changed()
    assert w.save_editor()
    saved = w.project.get("utterances", r["id"])
    assert saved["character_ids"] == [a, b] and saved["notes"] == "新增备注"


def test_undo_is_not_overwritten_by_stale_editor(window):
    w, r, a, b = window
    w.original.setPlainText("人工修改")
    w.save_editor()
    w.history(False)
    w.refresh_rows()
    assert w.project.get("utterances", r["id"])["original"] == "人工原文"
    assert w.original.toPlainText() == "人工原文"


def test_invalid_time_is_kept_visible_and_not_saved(window):
    w, r, a, b = window
    w.end.setText("00:00:00")
    w.editor_changed()
    w.refresh_rows()
    assert w.end.text() == "00:00:00" and w.project.get("utterances", r["id"])["end_ms"] == 3000
    w.end.setText("00:00:03")
    w.editor_changed()
    w.save_editor()


def test_new_video_seek_waits_for_loaded_seekable_media(window):
    from PySide6.QtMultimedia import QMediaPlayer

    w, r, a, b = window

    class Player:
        def __init__(self):
            self.status = QMediaPlayer.LoadingMedia
            self.can_seek = False
            self.position = None

        def duration(self):
            return 20000

        def isSeekable(self):
            return self.can_seek

        def mediaStatus(self):
            return self.status

        def setPosition(self, value):
            self.position = value

        def play(self):
            pass

        def stop(self):
            pass

    w.player = Player()
    w.seek_video(12345)
    w.duration_changed(20000)
    assert w.pending_seek == 12345 and w.player.position is None
    w.player.status = QMediaPlayer.LoadedMedia
    w.player.can_seek = True
    w.media_status_changed(w.player.status)
    assert w.pending_seek is None and w.player.position == 12345
