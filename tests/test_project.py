import json

import pytest

from animedialog.domain import utterance
from animedialog.exporters import export_html, export_srt, export_txt
from animedialog.importers import (
    import_transcript,
    read_subtitles,
    read_transcript,
    role_names,
)
from animedialog.store import Project


@pytest.fixture
def project(tmp_path):
    p = Project(tmp_path / "中文 项目", "测试作品")
    p.add_episode(tmp_path / "第1集.mp4", "第1集")
    yield p
    p.close()


def add(p, **kw):
    values = dict(original="こんにちは", translation="你好")
    values.update(kw)
    r = utterance(p.episodes()[0]["id"], 1000, 4000, **values)
    p.put("utterances", r)
    return r


def test_review_states_are_independent_and_persist(project):
    r = add(project)
    c = project.character("彩叶")
    project.assign([r["id"]], c)
    changed = project.get("utterances", r["id"])
    assert changed["speaker_review"] == "confirmed"
    assert changed["text_review"] == "pending"
    reopened = Project(project.folder)
    assert reopened.get("utterances", r["id"]) == changed
    reopened.close()


def test_undo_redo_edit_then_diverge(project):
    r = add(project)
    project.edit(r["id"], original="修改")
    project.edit(r["id"], translation="译文修改")
    assert project.history_step()
    assert project.get("utterances", r["id"])["translation"] == "你好"
    assert project.history_step(True)
    assert project.get("utterances", r["id"])["translation"] == "译文修改"
    assert project.history_step()
    project.edit(r["id"], notes="新的操作")
    assert not project.history_step(True)


def test_new_asr_is_proposal_not_overwrite(project):
    r = add(project)
    project.edit(r["id"], original="人工已核对", text_review="confirmed")
    before = project.get("utterances", r["id"])
    project.suggest(r["id"], {"original": "机器猜测"})
    assert project.get("utterances", r["id"]) == before
    p = project.proposals()[0]
    project.accept_proposal(p["id"])
    assert project.get("utterances", r["id"])["original"] == "机器猜测"
    assert project.history_step()
    assert project.get("utterances", r["id"])["original"] == "人工已核对"


def test_split_and_merge_preserve_text_and_undo(project):
    r = add(project, original="第一句第二句", translation="甲乙")
    project.split(r["id"], 2500, ("第一句", "第二句"), ("甲", "乙"))
    rows = project.rows()
    assert "".join(r["original"] for r in rows) == "第一句第二句"
    assert rows[0]["end_ms"] == rows[1]["start_ms"] == 2500
    project.merge_rows([r["id"] for r in rows])
    assert len(project.rows()) == 1
    assert project.history_step()
    assert len(project.rows()) == 2


def test_rename_and_merge_character_across_episodes(project):
    a = project.character("人物1")
    b = project.character("八千代")
    r = add(project, character_ids=[a])
    c = project.get("characters", a)
    c["name"] = "辉夜"
    project.commit("改名", [("characters", c, a)])
    assert project.role(project.get("utterances", r["id"])) == "辉夜"
    project.merge_characters(a, b)
    assert project.role(project.rows()[0]) == "八千代"
    assert project.history_step()
    assert project.role(project.rows()[0]) == "辉夜"


def test_legacy_import_preserves_multi_turns_and_machine(tmp_path, project):
    original = [
        dict(
            id="0001",
            start=1,
            end=4,
            jp="甲乙",
            zh="甲\n乙",
            kind="对白",
            role="彩叶／辉夜",
            confirmed=False,
            flags=[],
            speaker_turns=[dict(role="彩叶", text="甲"), dict(role="辉夜", text="乙")],
        )
    ]
    p = tmp_path / "旧台词.json"
    p.write_text(json.dumps(original, ensure_ascii=False), encoding="utf8")
    assert import_transcript(project, p) == (1, 0)
    r = project.rows()[0]
    assert r["machine"] == original[0]
    assert len(r["turns"]) == 2
    assert r["turns"][0]["start_ms"] is None
    assert import_transcript(project, p) == (0, 0)
    assert role_names("御门晶（现实身份／回忆）／彩叶") == ["御门晶（现实身份／回忆）", "彩叶"]


def test_html_roundtrip_and_conflict_does_not_apply(project, tmp_path):
    add(project)
    p = tmp_path / "对照.html"
    export_html(project, project.rows(), p)
    payload = read_transcript(p)
    payload["rows"][0]["original"] = "网页修改"
    p.write_text(
        p.read_text(encoding="utf8").replace(
            json.dumps(read_transcript(p), ensure_ascii=False).replace("<", "\\u003c"),
            json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c"),
        ),
        encoding="utf8",
    )
    assert import_transcript(project, p) == (0, 1)
    assert project.rows()[0]["original"] == "こんにちは"


def test_html_script_escape(project, tmp_path):
    add(project, original="</script><script>alert(1)</script>")
    p = tmp_path / "out.html"
    export_html(project, project.rows(), p)
    assert p.read_text(encoding="utf8").count("</script>") == 2
    assert read_transcript(p)["rows"][0]["original"].startswith("</script>")


def test_srt_per_episode_and_millisecond_times(project, tmp_path):
    add(project)
    ep = project.add_episode(tmp_path / "第二集.mp4")
    r = utterance(ep["id"], 2345, 3456, original="句子")
    project.put("utterances", r)
    paths = export_srt(project, project.rows(), tmp_path / "字幕.srt", speaker=False)
    assert len(paths) == 2
    assert any("00:00:02,345" in p.read_text(encoding="utf-8-sig") for p in paths)


def test_subtitles_ass_commas_and_repeated_captions(tmp_path):
    p = tmp_path / "例.ass"
    p.write_text(
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:01.23,0:00:03.00,Default,人物甲,0,0,0,,你好,世界\\N第二行",
        encoding="utf8",
    )
    s = read_subtitles(p)
    assert s[0]["text"] == "你好,世界\n第二行"
    assert s[0]["start_ms"] == 1230


def test_bad_split_times_rejected(project):
    r = add(project)
    with pytest.raises(ValueError):
        project.split(r["id"], 0, ("", ""), ("", ""))
    with pytest.raises(ValueError):
        project.edit(r["id"], end_ms=0)


def test_grouped_turns_do_not_duplicate_other_people(project, tmp_path):
    a = project.character("甲")
    b = project.character("乙")
    add(
        project,
        character_ids=[a, b],
        turns=[dict(text="甲的话", character_id=a), dict(text="乙的话", character_id=b)],
    )
    p = tmp_path / "分组.txt"
    export_txt(project, project.rows(), p, True)
    s = p.read_text(encoding="utf-8-sig")
    section = s.split("甲\n" + "=" * 30, 1)[1].split("\n\n乙\n", 1)[0]
    assert "中文：甲的话" in section and "中文：乙的话" not in section


def test_merge_retains_turns_notes_and_known_times(project):
    a = project.character("甲")
    b = project.character("乙")
    r = add(project, character_ids=[a], notes="首句备注", speaker_review="confirmed")
    s = utterance(
        r["episode_id"],
        5000,
        7000,
        translation="乙的话",
        character_ids=[b],
        notes="次句备注",
        turns=[dict(text="乙的话", character_id=b, start_ms=None, end_ms=None)],
    )
    project.put("utterances", s)
    project.merge_rows([r["id"], s["id"]])
    merged = project.rows()[0]
    assert [t["character_id"] for t in merged["turns"]] == [a, b]
    assert merged["turns"][0]["start_ms"] == 1000 and merged["turns"][1]["start_ms"] is None
    assert merged["notes"] == "首句备注\n次句备注"
    project.history_step()
    assert (
        project.get("utterances", r["id"])["turns"] == []
        and not project.get("utterances", s["id"])["deleted"]
    )


def test_translation_edit_reconciles_turns_without_false_confirmation(project):
    a = project.character("甲")
    b = project.character("乙")
    r = add(
        project,
        translation="甲的话\n乙的话",
        character_ids=[a, b],
        speaker_review="confirmed",
        turns=[
            dict(text="甲的话", character_id=a, review="confirmed"),
            dict(text="乙的话", character_id=b, review="confirmed"),
        ],
    )
    project.edit(r["id"], translation="甲修改\n乙的话")
    changed = project.get("utterances", r["id"])
    assert changed["turns"][0]["text"] == "甲修改" and changed["turns"][0]["review"] == "pending"
    project.edit(r["id"], translation="合为整句")
    assert project.get("utterances", r["id"])["turns"] == []
    project.history_step()
    assert project.get("utterances", r["id"])["turns"][0]["text"] == "甲修改"


def test_character_merge_retains_cross_episode_voice_centers_and_undo(project):
    a = project.character("临时人物")
    b = project.character("目标人物")
    project.set_meta("voice_clusters", [dict(character_id=a, vector=[1, 0])])
    project.merge_characters(a, b)
    assert project.meta("voice_clusters")[0]["character_id"] == b
    project.history_step()
    assert project.meta("voice_clusters")[0]["character_id"] == a


def test_selected_person_export_does_not_include_other_turns(project, tmp_path):
    a = project.character("甲")
    b = project.character("乙")
    add(
        project,
        character_ids=[a, b],
        turns=[dict(text="甲的话", character_id=a), dict(text="乙的话", character_id=b)],
    )
    path = tmp_path / "只甲.txt"
    export_txt(project, project.rows(), path, True, a)
    text = path.read_text(encoding="utf-8-sig")
    assert "甲的话" in text and "乙的话" not in text


def test_reimport_retains_separate_human_review_states_after_comparison(project, tmp_path):
    from animedialog.exporters import payload

    r = add(project)
    data = payload(project, project.rows())
    a = project.character("甲")
    data["characters"] = project.characters()
    data["rows"][0].update(
        character_ids=[a], speaker_review="confirmed", text_review="pending", notes="网页人工核对"
    )
    path = tmp_path / "网页结果.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf8")
    assert import_transcript(project, path) == (0, 1)
    assert project.get("utterances", r["id"])["speaker_review"] == "pending"
    project.accept_proposal(project.proposals()[0]["id"])
    saved = project.get("utterances", r["id"])
    assert saved["speaker_review"] == "confirmed" and saved["text_review"] == "pending"
    project.history_step()
    assert project.get("utterances", r["id"])["speaker_review"] == "pending"


def test_statistics_requires_human_references_and_keeps_machine_baseline(project):
    from animedialog.statistics import review_statistics

    a = project.character("甲")
    b = project.character("乙")
    r = add(
        project,
        original="你好啊",
        character_ids=[a],
        machine={"initial": {"original": "你好吗", "character_ids": [a]}},
    )
    initial = review_statistics(project)
    assert (
        initial["original_character_difference_rate"] is None
        and initial["speaker_disagreement_rate"] is None
    )
    project.edit(r["id"], text_review="confirmed", speaker_review="confirmed", character_ids=[b])
    stats = review_statistics(project)
    assert stats["original_character_edits"] == 1 and stats[
        "original_character_difference_rate"
    ] == pytest.approx(1 / 3)
    assert (
        stats["speaker_disagreement_rate"] == 1
        and project.rows()[0]["machine"]["initial"]["original"] == "你好吗"
    )


def test_voice_suggestion_does_not_invalidate_confirmed_text(project):
    a = project.character("甲")
    r = add(project, text_review="confirmed")
    project.suggest(r["id"], dict(character_ids=[a], evidence=["声音样本候选"]))
    project.accept_proposal(project.proposals()[0]["id"])
    saved = project.rows()[0]
    assert saved["speaker_review"] == "pending" and saved["text_review"] == "confirmed"
