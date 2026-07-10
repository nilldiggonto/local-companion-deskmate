import httpx

OLLAMA_URL = "http://localhost:11434"
CHAT_MODEL = "qwen2.5"
EMBED_MODEL = "nomic-embed-text"


async def chat(messages: list[dict], model: str = CHAT_MODEL) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{OLLAMA_URL}/api/chat",
            json={"model": model, "messages": messages, "stream": False},
            timeout=180.0,
        )
        response.raise_for_status()
        return response.json()["message"]["content"]


async def embed(text: str, model: str = EMBED_MODEL) -> list[float]:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": model, "prompt": text},
            timeout=60.0,
        )
        response.raise_for_status()
        return response.json()["embedding"]
