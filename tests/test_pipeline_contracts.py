import json
from pathlib import Path

import pytest

from animedialog.domain import utterance
from animedialog.engines import Cancelled, Control, Paused, transcribe
from animedialog.exporters import export_srt
from animedialog.importers import subtitle_target
from animedialog.pipeline import cached, ensure_space, process_job
from animedialog.store import Project


@pytest.fixture
def job(tmp_path):
    p = Project(tmp_path / "作品")
    ep = p.add_episode(tmp_path / "视频.mp4")
    j = p.new_job(ep["id"], {})
    yield p, j
    p.close()


def test_progress_does_not_replace_pause_request(job):
    p, j = job
    other = Project(p.folder)
    other.update_job(j["id"], request="pause")
    c = Control(p, j["id"])
    c.progress("测试", 30)
    assert p.get("jobs", j["id"])["request"] == "pause"
    with pytest.raises(Paused):
        c.check()
    other.update_job(j["id"], request="cancel")
    with pytest.raises(Cancelled):
        c.check()
    other.close()


def test_atomic_checkpoint_can_resume_without_rebuilding(tmp_path):
    path = tmp_path / "已完成.json"
    calls = []
    assert cached(path, lambda: calls.append(1) or {"rows": ["保留中文"]}) == {"rows": ["保留中文"]}
    assert cached(path, lambda: calls.append(2)) == {"rows": ["保留中文"]}
    assert calls == [1]


def test_space_failure_is_actionable(monkeypatch, tmp_path):
    from collections import namedtuple

    d = namedtuple("Disk", "total used free")
    monkeypatch.setattr("animedialog.pipeline.shutil.disk_usage", lambda _: d(100, 99, 1))
    with pytest.raises(OSError, match="磁盘空间不足"):
        ensure_space(tmp_path, 2)


def test_requested_pause_is_respected_at_worker_start(job):
    p, j = job
    p.update_job(j["id"], request="pause")
    assert process_job(p.folder, j["id"]) == 0
    assert p.get("jobs", j["id"])["state"] == "paused"


def test_missing_video_fails_without_removing_rows(job):
    p, j = job
    r = utterance(j["episode_id"], 100, 800, original="人工文字")
    p.put("utterances", r)
    assert process_job(p.folder, j["id"]) == 1
    assert p.rows()[0]["original"] == "人工文字"
    assert "视频不存在" in p.get("jobs", j["id"])["error"]


def test_gpu_failure_retries_cpu_and_retains_result(monkeypatch, tmp_path):
    import numpy as np
    import soundfile as sf

    audio = tmp_path / "声音.wav"
    sf.write(audio, np.ones(16000, dtype="float32") * 0.01, 16000)
    monkeypatch.setattr("animedialog.engines.require_model", lambda _: str(tmp_path / "模型.bin"))
    monkeypatch.setattr("animedialog.engines.executable", lambda _: "whisper-cli.exe")

    class Runner:
        def __init__(self):
            self.calls = []

        def progress(self, *_):
            pass

        def process(self, args, log):
            self.calls.append(args)
            if "-ng" not in args:
                raise RuntimeError("模拟驱动失败")
            Path(args[args.index("-of") + 1] + ".json").write_text(
                json.dumps(
                    {
                        "result": {"language": "ja"},
                        "transcription": [
                            {"text": "実際の音声", "offsets": {"from": 0, "to": 500}}
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf8",
            )

    control = Runner()
    rows, language = transcribe(audio, tmp_path / "结果", "auto", control)
    assert len(control.calls) == 2 and "-ng" in control.calls[1]
    assert language == "ja" and rows[0]["original"] == "実際の音声"


def test_digital_silence_is_not_hallucinated(monkeypatch, tmp_path):
    import numpy as np
    import soundfile as sf

    audio = tmp_path / "静音.wav"
    sf.write(audio, np.zeros(16000, dtype="float32"), 16000)
    monkeypatch.setattr("animedialog.engines.require_model", lambda _: "unused.bin")
    rows, language = transcribe(audio, tmp_path / "静音", "zh", None)
    assert rows == [] and language == "zh"


def test_subtitle_language_and_chinese_only_srt(tmp_path):
    assert subtitle_target("こんにちは", "ja") == "original"
    assert subtitle_target("你好", "ja") == "translation"
    assert subtitle_target("未来", "ja", "original") == "original"
    assert subtitle_target("你好", "zh") == "original"
    p = Project(tmp_path / "项目")
    ep = p.add_episode("中文.mp4")
    r = utterance(ep["id"], 1250, 2200, original="中文原声", language="zh")
    p.put("utterances", r)
    path = tmp_path / "中文.srt"
    export_srt(p, [r], path, language="zh", speaker=False)
    assert "中文原声" in path.read_text(encoding="utf-8-sig")
    p.close()


def test_same_episode_title_does_not_overwrite_srt(tmp_path):
    p = Project(tmp_path / "项目")
    for i in range(2):
        e = p.add_episode(str(i) + ".mp4", "同名")
        p.put("utterances", utterance(e["id"], 1000, 2000, original=str(i)))
    paths = export_srt(p, p.rows(), tmp_path / "字幕.srt")
    assert len(set(paths)) == 2
    assert all(path.exists() for path in paths)
    p.close()


def test_pipeline_saves_immutable_machine_version_before_human_edits(job, monkeypatch):
    import numpy as np
    import soundfile as sf

    from animedialog.pipeline import process_transcript

    p, j = job
    ep = p.get("episodes", j["episode_id"])
    cache = p.folder / "cache" / "fixture"
    cache.mkdir()
    monkeypatch.setattr(
        "animedialog.pipeline.probe",
        lambda _: dict(format={"duration": "2"}, streams=[{"codec_type": "audio", "index": 0}]),
    )
    monkeypatch.setattr(
        "animedialog.pipeline.transcribe",
        lambda *args: (
            [dict(start_ms=0, end_ms=1800, original="机器原文", flags=[], asr_confidence=0.9)],
            "ja",
        ),
    )

    class Runner(Control):
        def process(self, args, log):
            sf.write(args[-1], np.zeros(32000), 16000)

    process_transcript(p, ep, dict(speakers=False, semantic=False), cache, Runner(p, j["id"]))
    r = p.rows()[0]
    p.edit(r["id"], original="人工修正", text_review="confirmed")
    assert (
        p.rows()[0]["machine"]["initial"]["original"] == "机器原文"
        and p.rows()[0]["original"] == "人工修正"
    )
    cid = p.character("甲")
    p.edit(r["id"], character_ids=[cid], speaker_review="confirmed", translation="人工译文")
    another = p.folder / "cache" / "target"
    another.mkdir()
    process_transcript(
        p,
        ep,
        dict(target_ids=[r["id"]], large=True, speakers=False, semantic=False),
        another,
        Runner(p, j["id"]),
    )
    proposal = p.proposals()[0]
    assert "character_ids" not in proposal["data"] and "translation" not in proposal["data"]
    p.accept_proposal(proposal["id"])
    saved = p.rows()[0]
    assert (
        saved["translation"] == "人工译文"
        and saved["speaker_review"] == "confirmed"
        and saved["text_review"] == "pending"
    )
