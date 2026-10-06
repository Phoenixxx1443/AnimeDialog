"""Run: python -m scripts.test_clips (synthetic video, no models or network)."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
from PySide6.QtCore import QItemSelectionModel, QModelIndex, QTimer
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QLineEdit

from animedialog.domain import utterance
from animedialog.engines import Control
from animedialog.media import probe, run
from animedialog.pipeline import process_job
from animedialog.settings import executable
from animedialog.store import Project
from animedialog.ui import MainWindow


def main():
    with (
        TemporaryDirectory() as temporary,
        patch.dict(os.environ, ANIMEDIALOG_HOME=temporary, QT_QPA_PLATFORM="offscreen"),
    ):
        root = Path(temporary)
        ffmpeg = [executable("ffmpeg"), "-v", "error", "-y"]
        source = root / "原片 中文.mp4"
        blue = root / "无声另一集.mp4"
        result = run(
            ffmpeg
            + [
                "-f",
                "lavfi",
                "-i",
                "color=red:s=160x90:r=25:d=1.2",
                "-f",
                "lavfi",
                "-i",
                "color=green:s=160x90:r=25:d=1.8",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=3",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=880:duration=3",
                "-filter_complex",
                "[0:v][1:v]concat=n=2:v=1:a=0[v]",
                "-map",
                "[v]",
                "-map",
                "2:a",
                "-map",
                "3:a",
                "-c:v",
                "libx264",
                "-g",
                "250",
                "-sc_threshold",
                "0",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(source),
            ]
        )
        assert result.returncode == 0, result.stderr
        result = run(
            ffmpeg
            + ["-f", "lavfi", "-i", "color=blue:s=176x144:r=30:d=3", "-c:v", "libx264", str(blue)]
        )
        assert result.returncode == 0, result.stderr
        project = Project(root / "作品")
        episodes = [project.add_episode(source), project.add_episode(blue)]
        for i, ep in enumerate(episodes):
            ep.update(
                metadata=probe(ep["path"]), duration_ms=3000, audio_index=2 if i == 0 else None
            )
            project.put("episodes", ep)
        rows = [
            utterance(episodes[0]["id"], 100, 600, original="红色"),
            utterance(episodes[0]["id"], 1400, 2300, original="绿色/?"),
            utterance(episodes[1]["id"], 100, 900, original="蓝色无声"),
        ]
        for row in rows:
            project.put("utterances", row)
        folder = project.folder
        project.close()
        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        window = MainWindow(folder)
        window.start_next_job = lambda: None
        window.loading = True
        selection = window.table.selectionModel()
        for i in range(3):
            selection.select(
                window.table_model.index(i, 0),
                QItemSelectionModel.Select | QItemSelectionModel.Rows,
            )
        window.loading = False
        window.clips.add_selected()
        assert len(window.clips.items()) == 3 and window.right_tabs.currentIndex() == 1
        window.clips.move(-1)
        window.clips.move(-1)
        assert [c["text"] for c in window.clips.items()] == ["蓝色无声", "红色", "绿色/?"]
        model = window.clips.list.model()
        assert model.moveRow(QModelIndex(), 0, QModelIndex(), 3)
        assert window.project.meta("clip_draft") == window.clips.items()
        assert model.moveRow(QModelIndex(), 2, QModelIndex(), 0)

        def adjust_time():
            dialog = app.activeModalWidget()
            start, end = dialog.findChildren(QLineEdit)
            start.setText("00:00:00.200")
            end.setText("00:00:00.100")
            ok = dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok)
            with patch.object(window, "warn") as warning:
                ok.click()
                assert warning.called and dialog.isVisible()
            end.setText("00:00:01.000")
            ok.click()

        QTimer.singleShot(0, adjust_time)
        window.clips.edit_time()
        assert window.clips.items()[0]["start_ms"] == 200
        expected = window.clips.items()
        joined = root / "输出 中文" / "合辑.mp4"
        with patch("animedialog.clips.QFileDialog.getSaveFileName", return_value=(str(joined), "")):
            window.clips.export("joined")
        job = window.project.all("jobs")[0]
        window.clips.remove()
        assert len(window.project.get("jobs", job["id"])["options"]["clips"]) == 3
        window.focus_search()
        assert window.right_tabs.currentIndex() == 0
        window.close()
        project = Project(folder)
        assert len(project.meta("clip_draft")) == 2 and project.rows() == rows
        original_process = Control.process
        calls = []

        def track(self, args, log):
            calls.append(args[-1])
            return original_process(self, args, log)

        original_progress = Control.progress

        def pause_after_one(self, stage, value, message=""):
            original_progress(self, stage, value, message)
            if stage == "裁剪片段" and message.startswith("2/"):
                self.project.update_job(self.job_id, request="pause")

        with (
            patch.object(Control, "progress", pause_after_one),
            patch.object(Control, "process", track),
        ):
            assert process_job(folder, job["id"]) == 0
        assert project.get("jobs", job["id"])["state"] == "paused"
        cache = folder / "cache" / job["id"]
        assert len(list(cache.glob("clip-*.mkv"))) == 1 and not joined.exists()
        calls.clear()
        project.update_job(job["id"], request="run")
        with patch.object(Control, "process", track):
            assert process_job(folder, job["id"]) == 0
        assert sum(p.endswith(".mkv") for p in calls) == 2, calls
        assert abs(float(probe(joined)["format"]["duration"]) - 2.2) < 0.08
        for at, channel in [(0.3, 2), (1.0, 0), (1.8, 1)]:
            result = run(
                ffmpeg[:-1]
                + [
                    "-ss",
                    str(at),
                    "-i",
                    str(joined),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=1:1",
                    "-pix_fmt",
                    "rgb24",
                    "-f",
                    "rawvideo",
                    "pipe:1",
                ]
            )
            pixel = np.frombuffer(result.stdout, dtype=np.uint8)
            assert len(pixel) == 3 and pixel.argmax() == channel, (at, pixel)
        for at, silent in [(0.15, True), (1.0, False), (1.7, False)]:
            result = run(
                ffmpeg[:-1]
                + [
                    "-ss",
                    str(at),
                    "-i",
                    str(joined),
                    "-t",
                    "0.15",
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "8000",
                    "-f",
                    "s16le",
                    "pipe:1",
                ]
            )
            audio = np.frombuffer(result.stdout, dtype=np.int16).astype(float)
            if silent:
                assert np.max(np.abs(audio)) < 5
            else:
                frequency = np.fft.rfftfreq(len(audio), 1 / 8000)[
                    np.abs(np.fft.rfft(audio)).argmax()
                ]
                assert abs(frequency - 880) < 15, frequency
        before = joined.read_bytes()
        with patch("animedialog.pipeline.ensure_space", side_effect=OSError("disk full")):
            assert process_job(folder, job["id"]) == 0 and joined.read_bytes() == before
        joined.write_bytes(b"keep existing file")
        assert process_job(folder, job["id"]) == 1 and joined.read_bytes() == b"keep existing file"
        assert "未覆盖" in project.get("jobs", job["id"])["error"]
        separate = project.new_job(
            episodes[0]["id"],
            dict(
                task="clips",
                clips=expected,
                mode="separate",
                output=str(root / "分段"),
                max_height=720,
            ),
        )
        assert process_job(folder, separate["id"]) == 0
        outputs = sorted((root / "分段").glob("*.mp4"))
        assert len(outputs) == 3
        for path, seconds, size in zip(
            outputs, [0.8, 0.5, 0.9], [(176, 144), (160, 90), (160, 90)], strict=True
        ):
            metadata = probe(path)
            assert abs(float(metadata["format"]["duration"]) - seconds) < 0.07
            video = metadata["streams"][0]
            assert (video["width"], video["height"]) == size
        invalid = project.new_job(
            episodes[0]["id"],
            dict(
                task="clips",
                clips=[dict(expected[0], end_ms=5000)],
                mode="joined",
                output=str(root / "bad.mp4"),
            ),
        )
        assert process_job(folder, invalid["id"]) == 1 and not (root / "bad.mp4").exists()
        project.close()
    print(
        "Clip selection, ordering, immutable jobs, pause/resume, frame cuts, audio tracks, silent clips and safe export passed."
    )


if __name__ == "__main__":
    main()
