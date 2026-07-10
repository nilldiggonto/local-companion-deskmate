from contextlib import asynccontextmanager

from fastapi import FastAPI

from server.llm_client import chat
from server.memory import init_db, retrieve_relevant, save_memory
from server.models import ChatRequest, ChatResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    memories = await retrieve_relevant(request.message)

    system_content = "You are a helpful personal assistant."
    if memories:
        system_content += "\nHere is what you remember about the user:\n"
        system_content += "\n".join(f"- {m}" for m in memories)

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": request.message},
    ]
    reply = await chat(messages)

    await save_memory(request.message)

    return ChatResponse(reply=reply)
