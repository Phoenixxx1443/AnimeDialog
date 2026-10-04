"""Shared, versioned project records. Times are always integer milliseconds."""

import copy
import json
import re
import uuid
from datetime import datetime, timezone

KINDS = ["对白", "旁白", "歌词", "画面文字", "待核片段"]


def needs_review(row, mode="any"):
    """Use the same review rules for filtering, navigation and table colors."""
    speaker_pending = row["kind"] != "画面文字" and row["speaker_review"] != "confirmed"
    text_pending = row["text_review"] != "confirmed"
    if mode == "speaker":
        return speaker_pending
    if mode == "text":
        return text_pending
    return speaker_pending or text_pending


def uid():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc).isoformat()


def clone(value):
    return copy.deepcopy(value)


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def stamp(ms, srt=False):
    ms = max(0, round(ms))
    s, rem = divmod(ms, 1000)
    result = f"{s // 3600:02}:{s // 60 % 60:02}:{s % 60:02}"
    return result + (f",{rem:03}" if srt else f".{rem:03}")


def parse_stamp(text):
    pieces = str(text).strip().replace(",", ".").split(":")
    if len(pieces) > 3:
        raise ValueError("时间格式应为 时:分:秒.毫秒")
    try:
        return round(sum(float(v) * 60**i for i, v in enumerate(reversed(pieces))) * 1000)
    except ValueError:
        raise ValueError("请输入有效的时间")


def utterance(episode_id, start_ms, end_ms, **fields):
    result = dict(
        id=uid(),
        episode_id=episode_id,
        start_ms=round(start_ms),
        end_ms=round(end_ms),
        original="",
        translation="",
        language="auto",
        kind="对白",
        character_ids=[],
        speaker_review="pending",
        text_review="pending",
        evidence=[],
        flags=[],
        turns=[],
        notes="",
        revision=0,
        deleted=False,
        machine={},
        source="audio",
        translation_source="",
        legacy_id="",
    )
    result.update(fields)
    validate(result)
    return result


def validate(row):
    if not isinstance(row.get("start_ms"), int) or not isinstance(row.get("end_ms"), int):
        raise ValueError("时间必须按毫秒保存")
    if row["start_ms"] < 0 or row["end_ms"] <= row["start_ms"]:
        raise ValueError("结束时间必须晚于开始时间，开始时间不能为负数")
    if row["kind"] not in KINDS:
        raise ValueError("未知的内容类型")
    if row["speaker_review"] not in ["pending", "confirmed"] or row["text_review"] not in [
        "pending",
        "confirmed",
    ]:
        raise ValueError("无效的审核状态")
    for t in row.get("turns", []):
        a, b = t.get("start_ms"), t.get("end_ms")
        if (a is None) != (b is None):
            raise ValueError("分句起止时间须同时填写或同时留空")
        if a is not None and not row["start_ms"] <= a < b <= row["end_ms"]:
            raise ValueError("分句时间必须位于整段范围内")


def canonical_name(name):
    name = re.sub(r"（候选）|\(候选\)", "", name).strip()
    return name or "待确认"
