"""The memory bank: a local SQLite database of facts, sources, and past interactions."""
import json
import re
import sqlite3
import threading
import time
from dataclasses import dataclass

STOPWORDS = {
    "the", "and", "for", "are", "was", "what", "who", "when", "where", "why",
    "how", "which", "that", "this", "with", "from", "does", "did", "can", "you",
    "your", "about", "into", "have", "has", "had", "is", "of", "to", "in", "a",
}


def normalize(question):
    q = re.sub(r"[^\w\s]", "", question.lower())
    return re.sub(r"\s+", " ", q).strip()


@dataclass
class Fact:
    id: int
    content: str
    source: str
    trust: float
    created: float
    kind: str = "fact"
    jurisdiction: str | None = None
    as_of: str | None = None


class MemoryBank:
    def __init__(self, path="veritas_memory.db"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self._init_schema()

    def _init_schema(self):
        c = self.conn
        c.execute(
            """CREATE TABLE IF NOT EXISTS facts(
                id INTEGER PRIMARY KEY, content TEXT NOT NULL, source TEXT,
                trust REAL DEFAULT 0.8, created REAL, superseded_by INTEGER)"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS interactions(
                id INTEGER PRIMARY KEY, question TEXT, answer TEXT, confidence REAL,
                feedback TEXT, created REAL)"""
        )
        c.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, answer TEXT, created REAL)")
        # Upgrade databases created by older versions.
        self._add_column("facts", "kind", "TEXT DEFAULT 'fact'")
        self._add_column("facts", "jurisdiction", "TEXT")
        self._add_column("facts", "as_of", "TEXT")
        self._add_column("interactions", "model_calls", "INTEGER DEFAULT 0")
        had_index = c.execute("SELECT 1 FROM sqlite_master WHERE name='facts_fts'").fetchone() is not None
        try:
            c.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts "
                "USING fts5(content, content='facts', content_rowid='id')"
            )
            self.fts = True
            if not had_index:
                c.execute("INSERT INTO facts_fts(facts_fts) VALUES ('rebuild')")
        except sqlite3.OperationalError:
            self.fts = False
        c.commit()

    def _add_column(self, table, column, decl):
        cols = {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")

    def version(self):
        row = self.conn.execute("SELECT value FROM meta WHERE key='version'").fetchone()
        return int(row["value"]) if row else 0

    def _bump(self):
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES ('version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(self.version() + 1),),
        )

    # ---- facts -------------------------------------------------------------
    def add(self, content, source="user", trust=0.8, kind="fact", jurisdiction=None, as_of=None):
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO facts(content, source, trust, created, kind, jurisdiction, as_of) VALUES (?,?,?,?,?,?,?)",
                (content.strip(), source, trust, time.time(), kind, jurisdiction, as_of),
            )
            if self.fts:
                self.conn.execute("INSERT INTO facts_fts(rowid, content) VALUES (?,?)", (cur.lastrowid, content.strip()))
            self._bump()
            self.conn.commit()
            return cur.lastrowid

    def supersede(self, old_id, new_content, source="user correction", trust=0.95):
        with self.lock:
            new_id = self.add(new_content, source, trust, kind="correction")
            self.conn.execute("UPDATE facts SET superseded_by=? WHERE id=?", (new_id, old_id))
            self._bump()
            self.conn.commit()
            return new_id

    def forget(self, fact_id):
        with self.lock:
            row = self.conn.execute("SELECT content FROM facts WHERE id=?", (fact_id,)).fetchone()
            if not row:
                return False
            if self.fts:
                self.conn.execute(
                    "INSERT INTO facts_fts(facts_fts, rowid, content) VALUES ('delete', ?, ?)",
                    (fact_id, row["content"]),
                )
            self.conn.execute("DELETE FROM facts WHERE id=?", (fact_id,))
            self._bump()
            self.conn.commit()
            return True

    def sources(self):
        """Every loaded document with how many memory pieces it has."""
        return [dict(r) for r in self.conn.execute(
            """SELECT source, kind, jurisdiction, as_of, COUNT(*) AS pieces FROM facts
               WHERE superseded_by IS NULL GROUP BY source, kind, jurisdiction, as_of ORDER BY source"""
        )]

    def forget_source(self, source):
        """Remove every memory that came from one document, e.g. before reloading an updated law."""
        with self.lock:
            ids = [r["id"] for r in self.conn.execute("SELECT id FROM facts WHERE source=?", (source,))]
            for fid in ids:
                self.forget(fid)
            return len(ids)

    def get(self, fact_id):
        row = self.conn.execute("SELECT * FROM facts WHERE id=?", (fact_id,)).fetchone()
        return self._fact(row) if row else None

    def search(self, query, k=5):
        words = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 2 and w not in STOPWORDS]
        if not words:
            return []
        if self.fts:
            match = " OR ".join(f'"{w}"' for w in words)
            rows = self.conn.execute(
                """SELECT f.* FROM facts_fts JOIN facts f ON f.id = facts_fts.rowid
                   WHERE facts_fts MATCH ? AND f.superseded_by IS NULL
                   ORDER BY bm25(facts_fts) LIMIT ?""",
                (match, k),
            ).fetchall()
            return [self._fact(r) for r in rows]
        rows = self.conn.execute("SELECT * FROM facts WHERE superseded_by IS NULL").fetchall()
        scored = [(sum(w in r["content"].lower() for w in words), r) for r in rows]
        scored = sorted((s for s in scored if s[0]), key=lambda s: -s[0])
        return [self._fact(r) for _, r in scored[:k]]

    # ---- optional answer cache -------------------------------------------
    def cache_get(self, key):
        row = self.conn.execute("SELECT answer FROM cache WHERE key=?", (key,)).fetchone()
        return json.loads(row["answer"]) if row else None

    def cache_put(self, key, answer_dict):
        with self.lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO cache(key, answer, created) VALUES (?,?,?)",
                (key, json.dumps(answer_dict), time.time()),
            )
            self.conn.commit()

    # ---- interactions ------------------------------------------------------
    def log_interaction(self, question, answer, confidence, model_calls=0):
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO interactions(question, answer, confidence, created, model_calls) VALUES (?,?,?,?,?)",
                (question, answer, confidence, time.time(), model_calls),
            )
            self.conn.commit()
            return cur.lastrowid

    def get_interaction(self, interaction_id):
        return self.conn.execute("SELECT * FROM interactions WHERE id=?", (interaction_id,)).fetchone()

    def set_feedback(self, interaction_id, feedback):
        with self.lock:
            self.conn.execute("UPDATE interactions SET feedback=? WHERE id=?", (feedback, interaction_id))
            self.conn.commit()

    def stats(self):
        q = lambda sql: self.conn.execute(sql).fetchone()[0] or 0
        return {
            "facts": q("SELECT COUNT(*) FROM facts WHERE superseded_by IS NULL"),
            "official_sources": q("SELECT COUNT(*) FROM facts WHERE kind='official' AND superseded_by IS NULL"),
            "superseded_facts": q("SELECT COUNT(*) FROM facts WHERE superseded_by IS NOT NULL"),
            "questions_answered": q("SELECT COUNT(*) FROM interactions"),
            "total_ai_calls": q("SELECT SUM(model_calls) FROM interactions"),
            "corrections": q("SELECT COUNT(*) FROM interactions WHERE feedback LIKE 'corrected%'"),
        }

    @staticmethod
    def _fact(row):
        keys = row.keys()
        return Fact(
            row["id"], row["content"], row["source"], row["trust"], row["created"],
            row["kind"] if "kind" in keys and row["kind"] else "fact",
            row["jurisdiction"] if "jurisdiction" in keys else None,
            row["as_of"] if "as_of" in keys else None,
        )
