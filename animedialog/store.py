"""SQLite project store; undo/redo and machine suggestions never overwrite edits."""

import json
import sqlite3
from pathlib import Path

from .domain import clone, dumps, needs_review, now, uid, validate


class Project:
    def __init__(self, folder, title=None):
        self.folder = Path(folder).resolve()
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / "cache").mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.folder / "project.sqlite", timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS episodes(id TEXT PRIMARY KEY,data TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS characters(id TEXT PRIMARY KEY,data TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS utterances(id TEXT PRIMARY KEY,episode_id TEXT NOT NULL,
            start_ms INTEGER NOT NULL,end_ms INTEGER NOT NULL,deleted INTEGER NOT NULL,revision INTEGER NOT NULL,data TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS utterance_episode_time ON utterances(episode_id,start_ms);
          CREATE TABLE IF NOT EXISTS history(seq INTEGER PRIMARY KEY AUTOINCREMENT,label TEXT NOT NULL,
            changes TEXT NOT NULL,undone INTEGER NOT NULL DEFAULT 0,created TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,data TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS samples(id TEXT PRIMARY KEY,data TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY,row_id TEXT NOT NULL,base_revision INTEGER,
            data TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending');
        """)
        if self.meta("schema") is None:
            self.set_meta("schema", 1)
            self.set_meta("id", uid())
            self.set_meta("title", title or self.folder.name)
        if self.meta("schema") != 1:
            raise ValueError("项目格式版本不受支持")

    def close(self):
        self.db.close()

    def meta(self, key, default=None):
        r = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(r[0]) if r else default

    def set_meta(self, key, value):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (key, dumps(value)))

    def all(self, table):
        assert table in ["episodes", "characters", "jobs", "samples"]
        return [json.loads(r[0]) for r in self.db.execute(f"SELECT data FROM {table}")]

    def get(self, table, id):
        if table == "meta":
            value = self.meta(id)
            return dict(id=id, value=value) if value is not None else None
        assert table in ["episodes", "characters", "jobs", "samples", "utterances"]
        r = self.db.execute(f"SELECT data FROM {table} WHERE id=?", (id,)).fetchone()
        return json.loads(r[0]) if r else None

    def _put(self, table, item):
        if table == "meta":
            self.db.execute(
                "INSERT OR REPLACE INTO meta VALUES(?,?)", (item["id"], dumps(item["value"]))
            )
        elif table == "utterances":
            validate(item)
            self.db.execute(
                "INSERT OR REPLACE INTO utterances VALUES(?,?,?,?,?,?,?)",
                (
                    item["id"],
                    item["episode_id"],
                    item["start_ms"],
                    item["end_ms"],
                    int(item["deleted"]),
                    item["revision"],
                    dumps(item),
                ),
            )
        else:
            assert table in ["episodes", "characters", "jobs", "samples"]
            self.db.execute(
                f"INSERT OR REPLACE INTO {table} VALUES(?,?)", (item["id"], dumps(item))
            )

    def put(self, table, item):
        with self.db:
            self._put(table, item)

    def episodes(self):
        return sorted(self.all("episodes"), key=lambda e: e["number"])

    def characters(self):
        return sorted(self.all("characters"), key=lambda c: c["name"])

    def character(self, name):
        for c in self.characters():
            if name == c["name"] or name in c.get("aliases", []):
                return c["id"]
        c = dict(id=uid(), name=name, aliases=[], notes="")
        self.put("characters", c)
        return c["id"]

    def role(self, row):
        lookup = {c["id"]: c["name"] for c in self.characters()}
        return "／".join(lookup.get(c, "待确认") for c in row.get("character_ids", [])) or "待确认"

    def rows(self, episode=None, character=None, kind=None, query="", pending=None):
        sql = "SELECT data FROM utterances WHERE deleted=0"
        args = []
        if episode:
            sql += " AND episode_id=?"
            args.append(episode)
        sql += " ORDER BY start_ms,id"
        rows = [json.loads(x[0]) for x in self.db.execute(sql, args)]
        if character:
            rows = [
                r
                for r in rows
                if character in r["character_ids"]
                or any(t.get("character_id") == character for t in r.get("turns", []))
            ]
        if kind:
            rows = [r for r in rows if r["kind"] == kind]
        if query:
            q = query.casefold()
            names = {c["id"]: c["name"] for c in self.characters()}
            rows = [
                r
                for r in rows
                if q
                in (
                    r["original"]
                    + " "
                    + r["translation"]
                    + " "
                    + r["notes"]
                    + " "
                    + r.get("legacy_id", "")
                    + " "
                    + " ".join(names.get(c, "") for c in r["character_ids"])
                ).casefold()
            ]
        if pending in ("speaker", "text", "any"):
            rows = [r for r in rows if needs_review(r, pending)]
        order = {e["id"]: e["number"] for e in self.episodes()}
        return sorted(
            rows, key=lambda r: (order.get(r["episode_id"], 0), r["start_ms"], r["end_ms"])
        )

    def commit(self, label, changes):
        """changes: sequence of (table, new-record or None, id-for-delete)."""
        history = []
        with self.db:
            for table, new, id in changes:
                before = self.get(table, id)
                if new is not None:
                    new = clone(new)
                    if table == "utterances":
                        new["revision"] = (before or {}).get("revision", 0) + 1
                    self._put(table, new)
                else:
                    self.db.execute(
                        f"DELETE FROM {table} WHERE " + ("key" if table == "meta" else "id") + "=?",
                        (id,),
                    )
                history.append(dict(table=table, id=id, before=before, after=new))
            if history:
                self.db.execute("DELETE FROM history WHERE undone=1")
                self.db.execute(
                    "INSERT INTO history(label,changes,created) VALUES(?,?,?)",
                    (label, dumps(history), now()),
                )

    def edit(self, id, **fields):
        row = self.get("utterances", id)
        if row is None:
            raise ValueError("台词已不存在")
        if (
            row["turns"]
            and "translation" in fields
            and fields["translation"] != row["translation"]
            and "turns" not in fields
        ):
            lines = [s for s in fields["translation"].splitlines() if s.strip()]
            turns = clone(row["turns"])
            if len(lines) == len(turns):
                for t, text in zip(turns, lines):
                    if text != t.get("text", ""):
                        t.update(text=text, review="pending")
                fields["turns"] = turns
            else:
                fields["turns"] = []
                fields["flags"] = list(
                    dict.fromkeys(
                        row["flags"]
                        + ["整段中文结构已修改，请重新分句核对人物；旧分句可通过撤销恢复"]
                    )
                )
            fields["speaker_review"] = "pending"
        row.update(fields)
        self.commit("编辑台词", [("utterances", row, id)])

    def history_step(self, redo=False):
        entry = self.db.execute(
            "SELECT * FROM history WHERE undone=? ORDER BY seq "
            + ("ASC" if redo else "DESC")
            + " LIMIT 1",
            (int(redo),),
        ).fetchone()
        if not entry:
            return False
        with self.db:
            changes = json.loads(entry["changes"])
            for change in changes if redo else reversed(changes):
                item = change["after" if redo else "before"]
                table = change["table"]
                id = change["id"]
                if item is None:
                    self.db.execute(
                        f"DELETE FROM {table} WHERE " + ("key" if table == "meta" else "id") + "=?",
                        (id,),
                    )
                else:
                    item = clone(item)
                    if table == "utterances":
                        item["revision"] = (self.get(table, id) or {}).get("revision", 0) + 1
                    self._put(table, item)
            self.db.execute(
                "UPDATE history SET undone=? WHERE seq=?", (0 if redo else 1, entry["seq"])
            )
        return True

    def assign(self, ids, character_id, confirm=True):
        changes = []
        for id in ids:
            r = self.get("utterances", id)
            r["character_ids"] = [character_id] if character_id else []
            r["speaker_review"] = "confirmed" if character_id and confirm else "pending"
            r["turns"] = []
            r["evidence"] = ["人工核对整段人物归属"]
            changes.append(("utterances", r, id))
        self.commit("批量归类", changes)

    def merge_characters(self, source, target):
        if source == target:
            raise ValueError("请选择不同的人物")
        changes = []
        for r in self.rows():
            if source in r["character_ids"] or any(
                t.get("character_id") == source for t in r["turns"]
            ):
                r["character_ids"] = list(
                    dict.fromkeys(target if c == source else c for c in r["character_ids"])
                )
                for t in r["turns"]:
                    if t.get("character_id") == source:
                        t["character_id"] = target
                changes.append(("utterances", r, r["id"]))
        dest = self.get("characters", target)
        src = self.get("characters", source)
        dest["aliases"] = list(
            dict.fromkeys(dest.get("aliases", []) + [src["name"]] + src.get("aliases", []))
        )
        changes += [("characters", dest, target), ("characters", None, source)]
        for s in self.all("samples"):
            if s["character_id"] == source:
                s["character_id"] = target
                changes.append(("samples", s, s["id"]))
        centers = self.meta("voice_clusters", [])
        if any(c["character_id"] == source for c in centers):
            for c in centers:
                if c["character_id"] == source:
                    c["character_id"] = target
            changes.append(("meta", dict(id="voice_clusters", value=centers), "voice_clusters"))
        self.commit("合并人物", changes)

    def split(self, id, cut_ms, original_parts, translation_parts):
        row = self.get("utterances", id)
        if not row["start_ms"] < cut_ms < row["end_ms"]:
            raise ValueError("拆分位置须在台词范围内")
        left, right = clone(row), clone(row)
        right["id"] = uid()
        left["end_ms"] = cut_ms
        right["start_ms"] = cut_ms
        for i, r in enumerate([left, right]):
            r["original"] = original_parts[i]
            r["translation"] = translation_parts[i]
            r["turns"] = []
            r["machine"]["split_from"] = id
            r["speaker_review"] = r["text_review"] = "pending"
        self.commit("拆分台词", [("utterances", left, id), ("utterances", right, right["id"])])

    def merge_rows(self, ids):
        rows = sorted([self.get("utterances", i) for i in ids], key=lambda r: r["start_ms"])
        if len(rows) < 2 or len({r["episode_id"] for r in rows}) != 1:
            raise ValueError("请选择同一集中的至少两条台词")
        r = clone(rows[0])
        r["end_ms"] = max(x["end_ms"] for x in rows)
        r["original"] = "\n".join(x["original"] for x in rows)
        r["translation"] = "\n".join(x["translation"] for x in rows)
        r["character_ids"] = list(dict.fromkeys(c for x in rows for c in x["character_ids"]))
        r["speaker_review"] = r["text_review"] = "pending"
        r["turns"] = []
        for x in rows:
            if x["turns"]:
                r["turns"].extend(clone(x["turns"]))
            else:
                r["turns"].append(
                    dict(
                        text=x["translation"] or x["original"],
                        character_id=x["character_ids"][0]
                        if len(x["character_ids"]) == 1
                        else None,
                        start_ms=x["start_ms"],
                        end_ms=x["end_ms"],
                        review=x["speaker_review"],
                    )
                )
        r["notes"] = "\n".join(dict.fromkeys(x["notes"] for x in rows if x["notes"]))
        r["evidence"] = list(dict.fromkeys(v for x in rows for v in x["evidence"]))
        r["flags"] = list(dict.fromkeys(v for x in rows for v in x["flags"]))
        if len({x["kind"] for x in rows}) > 1:
            r["flags"].append("合并前内容类型不同，请复核类型")
        r["machine"]["merged_row_ids"] = [x["id"] for x in rows]
        changes = [("utterances", r, r["id"])]
        for x in rows[1:]:
            x["deleted"] = True
            changes.append(("utterances", x, x["id"]))
        self.commit("合并台词", changes)

    def suggest(self, id, candidate, base_revision=None, source="machine"):
        r = self.get("utterances", id)
        if not r:
            return
        candidate = clone(candidate)
        candidate["__proposal_source"] = source
        with self.db:
            self.db.execute(
                "INSERT INTO proposals VALUES(?,?,?,?,?)",
                (
                    uid(),
                    id,
                    r["revision"] if base_revision is None else base_revision,
                    dumps(candidate),
                    "pending",
                ),
            )

    def proposals(self):
        return [
            dict(x, data=json.loads(x["data"]))
            for x in self.db.execute("SELECT * FROM proposals WHERE status='pending'")
        ]

    def accept_proposal(self, id):
        p = self.db.execute("SELECT * FROM proposals WHERE id=?", (id,)).fetchone()
        if not p:
            return
        r = self.get("utterances", p["row_id"])
        candidate = json.loads(p["data"])
        source = candidate.pop("__proposal_source", "machine")
        protected = ["id", "episode_id", "revision"] + (["deleted"] if source != "import" else [])
        candidate = {k: v for k, v in candidate.items() if k not in protected}
        r.update(candidate)
        if source != "import":
            if any(k in candidate for k in ["character_ids", "turns", "start_ms", "end_ms"]):
                r["speaker_review"] = "pending"
            if any(
                k in candidate for k in ["original", "translation", "turns", "start_ms", "end_ms"]
            ):
                r["text_review"] = "pending"
        self.commit("接受识别建议", [("utterances", r, r["id"])])
        with self.db:
            self.db.execute("UPDATE proposals SET status='accepted' WHERE id=?", (id,))

    def add_episode(self, path, title=None):
        ep = dict(
            id=uid(),
            title=title or Path(path).stem,
            path=str(Path(path).resolve()),
            number=len(self.episodes()) + 1,
            duration_ms=0,
            language="auto",
            audio_index=None,
            subtitle_indices=[],
            attached=[],
            ocr_regions=[],
            metadata={},
        )
        self.put("episodes", ep)
        return ep

    def new_job(self, episode_id, options):
        job = dict(
            id=uid(),
            episode_id=episode_id,
            options=clone(options),
            state="queued",
            stage="",
            progress=0,
            error="",
            created=now(),
            updated=now(),
            request="run",
        )
        self.put("jobs", job)
        return job

    def update_job(self, id, **fields):
        # Atomic patches keep a UI pause/cancel request from being lost to worker progress.
        with self.db:
            self.db.execute(
                "UPDATE jobs SET data=json_patch(data,?) WHERE id=?", (dumps(fields), id)
            )
