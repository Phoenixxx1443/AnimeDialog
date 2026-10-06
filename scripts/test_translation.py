"""Run with: python -m scripts.test_translation (Windows, no network or models needed)."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx

from animedialog.domain import utterance
from animedialog.pipeline import process_job
from animedialog.settings import protected_key, save_settings, translation_endpoint
from animedialog.store import Project


def main():
    with (
        TemporaryDirectory() as folder,
        patch.dict(os.environ, ANIMEDIALOG_HOME=folder, QT_QPA_PLATFORM="offscreen"),
    ):
        url = translation_endpoint("https://example.test/v1/")
        assert url == "https://example.test/v1/chat/completions"
        for bad in ["http://example.test/v1", "https://key@host/v1", "https://host/v1?key=secret"]:
            try:
                translation_endpoint(bad)
            except ValueError:
                pass
            else:
                raise AssertionError("Unsafe endpoint accepted")
        key = "test-only-api-key"
        encrypted = protected_key(key)
        assert key not in encrypted and protected_key(encrypted, decrypt=True) == key
        config = dict(mode="api", url=url, model="test-model")
        save_settings(dict(translation=config, translation_keys={url: encrypted}))
        project = Project(Path(folder) / "作品")
        ep = project.add_episode("missing.mp4")
        cid = project.character("人物A")
        rows = [
            utterance(
                ep["id"],
                i * 1000,
                i * 1000 + 900,
                original="こんにちは",
                language="ja",
                character_ids=[cid],
                speaker_review="confirmed",
                text_review="confirmed",
            )
            for i in range(6)
        ]
        rows[1].update(translation="旧人工译文", translation_source="人工翻译")
        rows[3].update(original="中文原声", language="zh")
        rows[4].update(original="")
        rows[5].update(
            translation="甲\n乙",
            turns=[
                dict(text=t, character_id=cid, start_ms=None, end_ms=None, review="confirmed")
                for t in ["甲", "乙"]
            ],
        )
        for row in rows:
            project.put("utterances", row)
        job = project.new_job(
            ep["id"], dict(task="translate", target_ids=[r["id"] for r in rows], translator=config)
        )
        calls = []

        def reply(request):
            assert str(request.url) == url and request.headers["Authorization"] == "Bearer " + key
            body = json.loads(request.content)
            assert body["model"] == "test-model" and "chat_template_kwargs" not in body
            prompt = body["messages"][1]["content"]
            targets = json.loads(prompt.split("目标编号:")[1].split("\n上下文:")[0])
            calls.append(targets)
            if len(calls) == 1:
                other = Project(project.folder)
                other.edit(rows[2]["id"], original="処理中に修正", translation="处理中人工译文")
                other.close()
                result = dict(items=[])
            else:
                result = dict(items=[dict(id=id, translation="你好 · " + id[:4]) for id in targets])
            return httpx.Response(
                200, json=dict(choices=[dict(message=dict(content=json.dumps(result)))])
            )

        client = httpx.Client
        with patch(
            "animedialog.engines.httpx.Client",
            side_effect=lambda **kw: client(transport=httpx.MockTransport(reply), **kw),
        ):
            assert process_job(project.folder, job["id"]) == 0
            assert len(calls) == 2 and len(calls[0]) == 4
            assert process_job(project.folder, job["id"]) == 0 and len(calls) == 2
        a = project.get("utterances", rows[0]["id"])
        assert a["translation"].startswith("你好") and a["text_review"] == "pending"
        assert a["speaker_review"] == "confirmed" and a["original"] == rows[0]["original"]
        assert project.get("utterances", rows[1]["id"])["translation"] == "旧人工译文"
        assert project.get("utterances", rows[2]["id"])["translation"] == "处理中人工译文"
        assert not project.get("utterances", rows[3]["id"])["translation"]
        proposals = project.proposals()
        assert len(proposals) == 3
        p = next(p for p in proposals if p["row_id"] == rows[5]["id"])
        project.accept_proposal(p["id"])
        assert not project.get("utterances", rows[5]["id"])["turns"]
        assert (
            project.history_step() and len(project.get("utterances", rows[5]["id"])["turns"]) == 2
        )
        assert project.history_step(True) and not project.get("utterances", rows[5]["id"])["turns"]

        for status in [401, 429]:
            failed = project.new_job(
                ep["id"], dict(task="translate", target_ids=[a["id"]], translator=config)
            )
            with patch(
                "animedialog.engines.httpx.Client",
                side_effect=lambda **kw: client(
                    transport=httpx.MockTransport(lambda _: httpx.Response(status, text=key)), **kw
                ),
            ):
                assert process_job(project.folder, failed["id"]) == 1
            error = project.get("jobs", failed["id"])["error"]
            assert str(status) in error and key not in error

        extra = [
            utterance(
                ep["id"], 10000 + i * 1000, 10900 + i * 1000, original="Good morning", language="en"
            )
            for i in range(9)
        ]
        for row in extra:
            project.put("utterances", row)
        paused = project.new_job(
            ep["id"], dict(task="translate", target_ids=[r["id"] for r in extra], translator=config)
        )
        count = 0

        def interrupt(request):
            nonlocal count
            count += 1
            if count == 2:
                other = Project(project.folder)
                other.update_job(paused["id"], request="pause")
                other.close()
            targets = json.loads(
                json.loads(request.content)["messages"][1]["content"]
                .split("目标编号:")[1]
                .split("\n上下文:")[0]
            )
            result = dict(items=[dict(id=id, translation="早上好") for id in targets])
            return httpx.Response(
                200, json=dict(choices=[dict(message=dict(content=json.dumps(result)))])
            )

        with patch(
            "animedialog.engines.httpx.Client",
            side_effect=lambda **kw: client(transport=httpx.MockTransport(interrupt), **kw),
        ):
            assert process_job(project.folder, paused["id"]) == 0
            assert project.get("jobs", paused["id"])["state"] == "paused"
            assert sum(bool(project.get("utterances", r["id"])["translation"]) for r in extra) == 8
            project.update_job(paused["id"], request="run")
            assert process_job(project.folder, paused["id"]) == 0 and count == 3
            assert all(project.get("utterances", r["id"])["translation"] == "早上好" for r in extra)

        from PySide6.QtWidgets import QApplication

        from animedialog.dialogs import TranslationDialog
        from animedialog.ui import MainWindow

        app = QApplication.instance() or QApplication([])
        win = MainWindow(project.folder)
        win.select_record(rows[0]["id"])
        win.translation.setPlainText("手动输入")
        assert win.save_editor()
        assert project.get("utterances", rows[0]["id"])["translation_source"] == "人工翻译"
        win.notes.setText("只改备注")
        win.editor_changed()
        project.edit(rows[0]["id"], translation="后台补译", translation_source="机器翻译")
        assert win.save_editor()
        assert project.get("utterances", rows[0]["id"])["translation"] == "后台补译"
        dialog = TranslationDialog(win, 2, ep["title"])
        assert (
            dialog.key.text() == key and win.commands["translate"].shortcut().toString() == "Ctrl+T"
        )
        dialog.url.textEdited.emit("https://new.example.test/v1")
        assert not dialog.key.text()
        with (
            patch("animedialog.ui.TranslationDialog") as factory,
            patch.object(win, "start_next_job"),
        ):
            factory.return_value.exec.return_value = 1
            factory.return_value.scope.currentData.return_value = "selected"
            factory.return_value.config = config
            win.translate_original()
        queued = project.all("jobs")[-1]
        assert queued["options"]["task"] == "translate" and queued["options"]["target_ids"] == [
            a["id"]
        ]
        assert key not in json.dumps(queued) and queued["stage"] == "翻译原文"
        win.close()
        app.processEvents()
        for path in (project.folder / "cache").glob("**/*.json"):
            assert key not in path.read_text(encoding="utf8")
        assert key.encode() not in (project.folder / "project.sqlite").read_bytes()
        project.close()
    print("translation check passed")


if __name__ == "__main__":
    main()
