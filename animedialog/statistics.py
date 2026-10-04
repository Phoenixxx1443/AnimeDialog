"""Audit coverage and differences against human references; no invented accuracy."""

from collections import Counter

from .domain import now
from .importers import role_names


def distance(a, b):
    if a == b:
        return 0
    while a and b and a[0] == b[0]:
        a = a[1:]
        b = b[1:]
    while a and b and a[-1] == b[-1]:
        a = a[:-1]
        b = b[:-1]
    if len(a) > len(b):
        a, b = b, a
    previous = list(range(len(a) + 1))
    for i, y in enumerate(b, 1):
        row = [i]
        for j, x in enumerate(a, 1):
            row.append(min(row[-1] + 1, previous[j] + 1, previous[j - 1] + (x != y)))
        previous = row
    return previous[-1]


def review_statistics(project):
    rows = project.rows()
    chars = project.characters()
    valid = {c["id"] for c in chars}
    names = {name: c["id"] for c in chars for name in [c["name"]] + c.get("aliases", [])}
    text_rows = text_errors = edits = reference_chars = speaker_rows = speaker_errors = (
        skipped_long
    ) = 0
    for r in rows:
        machine = r.get("machine", {})
        initial = machine.get("initial", {})
        if machine.get("split_from") or machine.get("merged_row_ids"):
            continue
        original = initial.get("original", machine.get("jp", machine.get("asr_original")))
        if r["text_review"] == "confirmed" and original is not None and r["original"]:
            if max(len(original), len(r["original"])) > 5000:
                skipped_long += 1
            else:
                text_rows += 1
                text_errors += original != r["original"]
                edits += distance(original, r["original"])
                reference_chars += len(r["original"])
        if r["speaker_review"] == "confirmed":
            baseline = initial.get("character_ids")
            if baseline:
                baseline = [
                    c if c in valid else names.get(initial.get("character_names", {}).get(c))
                    for c in baseline
                ]
            else:
                baseline = [names.get(name) for name in role_names(machine.get("role", ""))]
            if baseline and all(baseline):
                speaker_rows += 1
                speaker_errors += set(baseline) != set(r["character_ids"])
    return dict(
        project_id=project.meta("id"),
        title=project.meta("title"),
        created=now(),
        records=len(rows),
        categories=dict(Counter(r["kind"] for r in rows)),
        human_speaker_confirmed=sum(r["speaker_review"] == "confirmed" for r in rows),
        human_text_confirmed=sum(r["text_review"] == "confirmed" for r in rows),
        speaker_pending=sum(r["speaker_review"] != "confirmed" for r in rows),
        text_pending=sum(r["text_review"] != "confirmed" for r in rows),
        flagged_records=sum(bool(r["flags"]) for r in rows),
        original_reference_rows=text_rows,
        original_changed_rows=text_errors,
        original_character_edits=edits,
        original_reference_characters=reference_chars,
        original_character_difference_rate=edits / reference_chars if reference_chars else None,
        speaker_reference_rows=speaker_rows,
        speaker_changed_rows=speaker_errors,
        speaker_disagreement_rate=speaker_errors / speaker_rows if speaker_rows else None,
        skipped_long_texts=skipped_long,
        interpretation="仅以人工审核条目作参考。人物候选与人工归属差异、原文字符编辑差异不等于已验证的全片准确度；中文译文需单独校对。",
    )
