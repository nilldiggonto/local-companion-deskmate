import json
import sqlite3
from pathlib import Path

from server.llm_client import embed
from server.similarity import cosine_similarity

DB_PATH = Path(__file__).parent.parent / "data" / "avatar.db"
SCHEMA_PATH = Path(__file__).parent / "db_schema.sql"


def get_connection() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    conn = get_connection()
    conn.executescript(SCHEMA_PATH.read_text())
    for column in ("success_count", "fail_count"):
        try:
            conn.execute(f"ALTER TABLE macros ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()


async def save_memory(text: str, tags: str | None = None) -> None:
    vector = await embed(text)
    conn = get_connection()
    conn.execute(
        "INSERT INTO memories (text, embedding, tags) VALUES (?, ?, ?)",
        (text, json.dumps(vector), tags),
    )
    conn.commit()
    conn.close()


def save_conversation(role: str, content: str) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO conversations (role, content) VALUES (?, ?)", (role, content)
    )
    conn.commit()
    conn.close()


def recent_conversation(limit: int = 8) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT role, content FROM conversations ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [{"role": role, "content": content} for role, content in reversed(rows)]


async def retrieve_relevant(query: str, top_k: int = 5) -> list[str]:
    query_vector = await embed(query)
    conn = get_connection()
    rows = conn.execute("SELECT text, embedding FROM memories").fetchall()
    conn.close()

    scored = [
        (text, cosine_similarity(query_vector, json.loads(embedding_json)))
        for text, embedding_json in rows
    ]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [text for text, _ in scored[:top_k]]
