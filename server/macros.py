import json

from server.llm_client import embed
from server.memory import get_connection
from server.similarity import cosine_similarity

_embedding_cache: dict[str, list[float]] = {}


async def _cached_embed(text: str) -> list[float]:
    if text not in _embedding_cache:
        _embedding_cache[text] = await embed(text)
    return _embedding_cache[text]


def save_macro(name: str, steps: list[dict], description: str | None = None) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO macros (name, description, steps) VALUES (?, ?, ?)",
        (name, description, json.dumps(steps)),
    )
    conn.commit()
    conn.close()


def get_macro(name: str) -> list[dict] | None:
    conn = get_connection()
    row = conn.execute("SELECT steps FROM macros WHERE name = ?", (name,)).fetchone()
    conn.close()
    if row is None:
        return None
    return json.loads(row[0])


def clear_all_macros() -> None:
    conn = get_connection()
    conn.execute("DELETE FROM macros")
    conn.commit()
    conn.close()


def delete_macro(name: str) -> bool:
    conn = get_connection()
    cursor = conn.execute("DELETE FROM macros WHERE name = ?", (name,))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0


def list_macros() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT name, description, success_count, fail_count FROM macros"
    ).fetchall()
    conn.close()
    return [
        {"name": name, "description": description, "success_count": s, "fail_count": f}
        for name, description, s, f in rows
    ]


def record_macro_result(name: str, success: bool) -> None:
    conn = get_connection()
    column = "success_count" if success else "fail_count"
    conn.execute(f"UPDATE macros SET {column} = {column} + 1 WHERE name = ?", (name,))
    conn.commit()
    conn.close()


async def match_macro(message: str) -> tuple[str | None, float]:
    """Returns (best macro name, similarity score). The caller decides what
    score is good enough -- auto-run, ask first, or ignore."""
    macros = list_macros()
    if not macros:
        return None, 0.0

    message_vector = await embed(message)

    best_name = None
    best_score = 0.0
    for macro in macros:
        macro_text = macro["description"] or macro["name"]
        macro_vector = await _cached_embed(macro_text)
        score = cosine_similarity(message_vector, macro_vector)
        if score > best_score:
            best_score = score
            best_name = macro["name"]

    return best_name, best_score
