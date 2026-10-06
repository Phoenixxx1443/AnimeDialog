"""Run: python -m scripts.test_simple_mode (no video, models or network needed)."""

import os
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from animedialog.domain import utterance
from animedialog.settings import settings
from animedialog.store import Project
from animedialog.ui import MainWindow


def main():
    with (
        TemporaryDirectory() as folder,
        patch.dict(os.environ, ANIMEDIALOG_HOME=folder, QT_QPA_PLATFORM="offscreen"),
        ExitStack() as cleanup,
    ):
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        project = Project(Path(folder) / "作品")
        episodes = [project.add_episode(f"第{i}集.mp4") for i in [1, 2]]
        cid = project.character("人物甲")
        rows = [
            utterance(
                ep["id"], 1000, 2000, original="原文", translation="中文", character_ids=[cid]
            )
            for ep in episodes
        ]
        rows[0]["kind"] = "歌词"
        for row in rows:
            project.put("utterances", row)
        project.close()
        window = MainWindow(Path(folder) / "作品")

        def close_window():
            window.editor_dirty = False
            window.close()

        cleanup.callback(close_window)
        window.show()
        app.processEvents()
        window.current_episode = episodes[0]["id"]
        window.kind.setCurrentText("歌词")
        window.refresh_rows()
        assert window.select_record(rows[0]["id"])
        window.start.setText("invalid")
        window.editor_changed()
        window.mode_toggle.click()
        assert not window.simple_mode and not window.mode_toggle.isChecked()
        assert window.editor.isVisible() and window.start.text() == "invalid"
        window.start.setText("00:00:01.000")
        window.original.setPlainText("已修改原文")
        window.mode_toggle.click()
        app.processEvents()
        assert window.simple_mode and window.commands["simple"].isChecked()
        assert all(not widget.isVisible() for widget in window.full_only)
        assert all(
            widget.isVisible()
            for widget in [window.characters, window.video_frame, window.table, window.mode_toggle]
        )
        assert not window.right_tabs.tabBar().isVisible() and window.right_tabs.currentIndex() == 0
        assert window.table.isColumnHidden(4) and window.table.isColumnHidden(5)
        assert window.current_episode is None and window.kind.currentIndex() == 0
        assert len(window.table_model.rows) == 2
        assert window.project.get("utterances", rows[0]["id"])["original"] == "已修改原文"
        pane_sizes = {
            key: list(widget.sizes())
            for key, widget in [
                ("sidebar", window.sidebar_splitter),
                ("player", window.center_splitter),
                ("review", window.review_splitter),
            ]
        }
        assert pane_sizes["sidebar"][0] == 0 and pane_sizes["player"][1] == 0
        window.characters.setCurrentRow(1)
        assert len(window.table_model.rows) == 2
        window.reset_layout()
        assert window.simple_mode and not window.editor.isVisible()
        window.focus_table()
        QTest.keyClick(window.table, Qt.Key_L, Qt.ControlModifier | Qt.ShiftModifier)
        app.processEvents()
        assert not window.simple_mode and not window.mode_toggle.isChecked()
        assert all(widget.isVisible() for widget in window.full_only)
        assert all(
            size > 0
            for widget in [window.sidebar_splitter, window.center_splitter, window.review_splitter]
            for size in widget.sizes()
        )
        window.set_simple_mode(True)
        window.commands["clips"].trigger()
        assert not window.simple_mode and window.clips.isVisible()
        window.set_simple_mode(True)
        window.focus_text(window.translation)
        assert not window.simple_mode and window.editor.isVisible()
        window.set_simple_mode(True)
        window.player_error()
        assert "视频播放失败" in window.video_hint.text() and window.video_hint.isVisible()
        before = window.project.rows()
        window.close()
        assert settings()["workspace"]["simple_mode"]
        window = MainWindow(Path(folder) / "作品")
        window.show()
        app.processEvents()
        assert window.simple_mode and window.mode_toggle.isChecked()
        assert not window.editor.isVisible() and window.table.isVisible()
        assert window.project.rows() == before
        window.mode_toggle.click()
        app.processEvents()
        assert window.editor.isVisible() and all(
            size > 0
            for widget in [window.sidebar_splitter, window.center_splitter, window.review_splitter]
            for size in widget.sizes()
        )
        window.close()
    print(
        "Simple mode toggle, shortcuts, save guards, filters, layout restoration and restart passed."
    )


if __name__ == "__main__":
    main()
