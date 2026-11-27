import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from backend.core.config import MEMORY_DB_PATH, MAX_MEMORY_MESSAGES, SUMMARY_TARGET_MESSAGES


@dataclass
class MemoryMessage:
    role: str
    content: str
    created_at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryStore:
    def __init__(self, db_path: str = MEMORY_DB_PATH) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        from pathlib import Path

        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def add_message(self, role: str, content: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO messages (role, content, created_at) VALUES (?, ?, ?)",
                (role, content, _now()),
            )

    def list_messages(self, limit: int = 100) -> List[MemoryMessage]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT role, content, created_at FROM messages ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [MemoryMessage(*row) for row in rows[::-1]]

    def count_messages(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            (count,) = conn.execute("SELECT COUNT(*) FROM messages").fetchone()
        return int(count)

    def get_summary(self) -> Optional[str]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT summary FROM summaries ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return row[0] if row else None

    def set_summary(self, summary: str, keep_recent: int = 0) -> None:
        """Store a rolling summary and trim history.

        Messages are only trimmed when ``keep_recent`` is 0 or the history is
        longer than that, so the exchange in flight is never discarded.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO summaries (summary, created_at) VALUES (?, ?)",
                (summary, _now()),
            )
            if keep_recent > 0:
                conn.execute(
                    """
                    DELETE FROM messages WHERE id NOT IN (
                        SELECT id FROM messages ORDER BY id DESC LIMIT ?
                    )
                    """,
                    (keep_recent,),
                )
            else:
                conn.execute("DELETE FROM messages")

    def reset(self) -> None:
        """Clear this account's transcript and rolling summaries."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM messages")
            conn.execute("DELETE FROM summaries")

    def maybe_summarize(self, summarizer, keep_recent: int = 0) -> Optional[str]:
        total = self.count_messages()
        if total <= MAX_MEMORY_MESSAGES:
            return None

        messages = self.list_messages(limit=total)
        transcript = "\n".join(f"{m.role}: {m.content}" for m in messages)
        previous = self.get_summary()
        prompt = (
            f"Earlier summary:\n{previous}\n\nNew messages:\n{transcript}"
            if previous
            else transcript
        )
        summary = summarizer(prompt, target_messages=SUMMARY_TARGET_MESSAGES)
        self.set_summary(summary, keep_recent=keep_recent)
        return summary

    def export_jsonl(self, path: str) -> None:
        messages = self.list_messages(limit=10000)
        with open(path, "w", encoding="utf-8") as handle:
            for msg in messages:
                handle.write(
                    json.dumps(
                        {
                            "role": msg.role,
                            "content": msg.content,
                            "created_at": msg.created_at,
                        }
                    )
                    + "\n"
                )
