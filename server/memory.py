import json
import sqlite3
from pathlib import Path

from server.llm_client import embed

DB_PATH = Path(__file__).parent.parent / "data" / "avatar.db"
SCHEMA_PATH = Path(__file__).parent / "db_schema.sql"


def get_connection() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    conn = get_connection()
    conn.executescript(SCHEMA_PATH.read_text())
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


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def retrieve_relevant(query: str, top_k: int = 5) -> list[str]:
    query_vector = await embed(query)
    conn = get_connection()
    rows = conn.execute("SELECT text, embedding FROM memories").fetchall()
    conn.close()

    scored = [
        (text, _cosine_similarity(query_vector, json.loads(embedding_json)))
        for text, embedding_json in rows
    ]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [text for text, _ in scored[:top_k]]
