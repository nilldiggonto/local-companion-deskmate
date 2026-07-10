import json

from server.llm_client import embed
from server.memory import get_connection
from server.similarity import cosine_similarity

MACRO_MATCH_THRESHOLD = 0.6


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


def list_macros() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT name, description FROM macros").fetchall()
    conn.close()
    return [{"name": name, "description": description} for name, description in rows]


async def find_matching_macro(message: str) -> str | None:
    macros = list_macros()
    if not macros:
        return None

    message_vector = await embed(message)

    best_name = None
    best_score = 0.0
    for macro in macros:
        macro_text = macro["description"] or macro["name"]
        macro_vector = await embed(macro_text)
        score = cosine_similarity(message_vector, macro_vector)
        if score > best_score:
            best_score = score
            best_name = macro["name"]

    if best_score >= MACRO_MATCH_THRESHOLD:
        return best_name
    return None
