import html
import json
import re
import uuid
from pathlib import Path

from .domain import canonical_name, clone, utterance


def role_names(text):
    result = []
    part = ""
    depth = 0
    for ch in text:
        if ch in "（(":
            depth += 1
        if ch in "）)":
            depth = max(0, depth - 1)
        if ch in "／/" and depth == 0:
            if part.strip():
                result.append(canonical_name(part))
                part = ""
        else:
            part += ch
    if part.strip():
        result.append(canonical_name(part))
    return [p for p in result if p not in ["待确认", "多人对话（待确认）", "画面说明"]]


def read_transcript(path):
    text = Path(path).read_text(encoding="utf-8-sig")
    if Path(path).suffix.lower() in [".html", ".htm"]:
        m = re.search(
            r'<script\b[^>]*\bid=["\'](?:animedialog-project|transcript-data)["\'][^>]*>(.*?)</script>',
            text,
            re.S | re.I,
        )
        if not m:
            raise ValueError(
                "网页中没有可导入的台词数据。请使用软件导出的 HTML 或之前的复核版 HTML。"
            )
        text = m.group(1)
    obj = json.loads(text)
    if isinstance(obj, list):
        return dict(schema=0, rows=obj, characters=[], episodes=[])
    if isinstance(obj, dict) and "rows" in obj:
        return obj
    raise ValueError("不支持的台词文件格式")


def import_transcript(project, path, episode_id=None):
    payload = read_transcript(path)
    schema = payload.get("schema", 0)
    if schema not in [0, 1]:
        raise ValueError("导出格式版本不受支持")
    conflicts = 0
    inserted = 0
    if schema == 1:
        for c in payload.get("characters", []):
            if not project.get("characters", c["id"]):
                project.put("characters", c)
        for ep in payload.get("episodes", []):
            if not project.get("episodes", ep["id"]):
                project.put("episodes", ep)
        for incoming in payload["rows"]:
            current = project.get("utterances", incoming["id"])
            if current:
                editable = [
                    "original",
                    "translation",
                    "start_ms",
                    "end_ms",
                    "kind",
                    "character_ids",
                    "turns",
                    "notes",
                    "speaker_review",
                    "text_review",
                    "evidence",
                    "flags",
                    "translation_source",
                    "deleted",
                ]
                changed = any(incoming.get(k) != current.get(k) for k in editable)
                if changed:
                    project.suggest(
                        current["id"],
                        {k: clone(incoming.get(k)) for k in editable},
                        incoming.get("base_revision", incoming.get("revision", 0)),
                        source="import",
                    )
                    conflicts += 1
            else:
                r = clone(incoming)
                r.pop("base_revision", None)
                project.put("utterances", r)
                inserted += 1
        return inserted, conflicts
    if not episode_id:
        import_path = str(Path(path).resolve())
        matching = next(
            (ep for ep in project.episodes() if ep.get("import_path") == import_path), None
        )
        if matching:
            episode_id = matching["id"]
        else:
            episode_id = project.add_episode("", Path(path).stem)["id"]
            ep = project.get("episodes", episode_id)
            ep["path"] = ""
            ep["import_path"] = import_path
            project.put("episodes", ep)
    for i, old in enumerate(payload["rows"]):
        legacy_id = str(old.get("id", i))
        id = str(uuid.uuid5(uuid.UUID(episode_id), legacy_id))
        name_list = role_names(old.get("role", "待确认"))
        character_ids = [project.character(n) for n in name_list]
        turns = []
        for t in old.get("speaker_turns", []) or []:
            who = canonical_name(t.get("role", "待确认"))
            turns.append(
                dict(
                    text=t.get("text", ""),
                    character_id=project.character(who) if who != "待确认" else None,
                    start_ms=None,
                    end_ms=None,
                    review="confirmed" if t.get("status") == "人工已确认" else "pending",
                )
            )
        r = utterance(
            episode_id,
            round(float(old["start"]) * 1000),
            round(float(old["end"]) * 1000),
            id=id,
            original=old.get("jp", ""),
            translation=old.get("zh", ""),
            kind=old.get("kind", "对白"),
            language="ja",
            character_ids=character_ids,
            turns=turns,
            machine=clone(old),
            source="legacy",
            translation_source="画面字幕",
            evidence=old.get("speaker_evidence", []) or [],
            flags=old.get("flags", []),
            legacy_id=legacy_id,
            speaker_review="confirmed"
            if old.get("manual_review") and old.get("confirmed")
            else "pending",
        )
        if project.get("utterances", id):
            current = project.get("utterances", id)
            editable = [
                "original",
                "translation",
                "start_ms",
                "end_ms",
                "kind",
                "character_ids",
                "turns",
                "speaker_review",
                "text_review",
                "evidence",
                "flags",
            ]
            if any(current[k] != r[k] for k in editable):
                project.suggest(id, r, source="import")
                conflicts += 1
        else:
            project.put("utterances", r)
            inserted += 1
    return inserted, conflicts


def subtitle_time(text):
    h, m, s = text.replace(",", ".").split(":")
    return round((int(h) * 3600 + int(m) * 60 + float(s)) * 1000)


def read_subtitles(path):
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = Path(path).read_text(encoding="gb18030")
    rows = []
    if Path(path).suffix.lower() in [".ass", ".ssa"]:
        format_fields = [
            "layer",
            "start",
            "end",
            "style",
            "name",
            "marginl",
            "marginr",
            "marginv",
            "effect",
            "text",
        ]
        in_events = False
        for line in text.splitlines():
            if line.startswith("["):
                in_events = line.strip().lower() == "[events]"
            if in_events and line.startswith("Format:"):
                format_fields = [s.strip().lower() for s in line.split(":", 1)[1].split(",")]
            if in_events and line.startswith("Dialogue:"):
                bits = line.split(":", 1)[1].split(",", len(format_fields) - 1)
                fields = dict(zip(format_fields, bits))
                if not all(k in fields for k in ["start", "end", "text"]):
                    continue
                caption = (
                    re.sub(r"\{[^}]*\}", "", fields["text"])
                    .replace(r"\N", "\n")
                    .replace(r"\n", "\n")
                    .replace(r"\h", " ")
                )
                rows.append(
                    dict(
                        start_ms=subtitle_time(fields["start"]),
                        end_ms=subtitle_time(fields["end"]),
                        text=caption,
                        speaker=fields.get("name", "").strip(),
                        source="外挂字幕",
                    )
                )
    else:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        for block in re.split(r"\n\s*\n", text):
            m = re.search(
                r"(\d+:\d{2}:\d{2}[,.]\d+)\s*-->\s*(\d+:\d{2}:\d{2}[,.]\d+)[^\n]*\n(.*)",
                block,
                re.S,
            )
            if m:
                rows.append(
                    dict(
                        start_ms=subtitle_time(m[1]),
                        end_ms=subtitle_time(m[2]),
                        text=html.unescape(re.sub("<[^>]+>", "", m[3].strip())),
                        speaker="",
                        source="外挂字幕",
                    )
                )
    return [r for r in rows if r["end_ms"] > r["start_ms"] and r["text"].strip()]


def align_subtitles(rows, subtitles, target="translation"):
    """Time overlap is the anchor. Unmatched captions remain explicit records."""
    used = set()
    result = clone(rows)
    for r in result:
        matches = []
        for i, s in enumerate(subtitles):
            overlap = min(r["end_ms"], s["end_ms"]) - max(r["start_ms"], s["start_ms"])
            if (
                overlap > 0
                and overlap / max(1, min(r["end_ms"] - r["start_ms"], s["end_ms"] - s["start_ms"]))
                > 0.30
            ):
                matches.append((i, s))
                used.add(i)
        if matches:
            if target == "original":
                r["machine"]["asr_original"] = r["original"]
                r["source"] = "subtitle+audio"
            texts = []
            for _, sub in matches:
                text = sub["text"]
                if texts and text in texts[-1]:
                    continue
                if texts and texts[-1] in text:
                    texts[-1] = text
                elif not texts or text != texts[-1]:
                    texts.append(text)
            r[target] = "\n".join(texts)
            if target == "translation":
                r["translation_source"] = matches[0][1]["source"]
            r["flags"].append("字幕按时间对齐，需核对声音边界")
    return result, [s for i, s in enumerate(subtitles) if i not in used]


def subtitle_target(text, language, hint="auto"):
    if hint in ["original", "translation"]:
        return hint
    if language in ["zh", "chinese"]:
        return "original"
    if re.search(r"[\u3040-\u30ff]", text):
        return "original"
    if re.search(r"[\u4e00-\u9fff]", text):
        return "translation"
    return "original"
