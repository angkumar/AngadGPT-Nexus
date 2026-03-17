import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional

from backend.core.config import MEMORY_DB_PATH, MAX_MEMORY_MESSAGES, SUMMARY_TARGET_MESSAGES


@dataclass
class MemoryMessage:
    role: str
    content: str
    created_at: str


class MemoryStore:
    def __init__(self, db_path: str = MEMORY_DB_PATH) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
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
        created_at = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO messages (role, content, created_at) VALUES (?, ?, ?)",
                (role, content, created_at),
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

    def set_summary(self, summary: str) -> None:
        created_at = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO summaries (summary, created_at) VALUES (?, ?)",
                (summary, created_at),
            )
            conn.execute("DELETE FROM messages")

    def maybe_summarize(self, summarizer) -> Optional[str]:
        total = self.count_messages()
        if total <= MAX_MEMORY_MESSAGES:
            return None

        messages = self.list_messages(limit=total)
        prompt = "\n".join([f"{m.role}: {m.content}" for m in messages])
        summary = summarizer(prompt, target_messages=SUMMARY_TARGET_MESSAGES)
        self.set_summary(summary)
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

