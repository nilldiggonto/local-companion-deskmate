import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from recorder.player import play_macro
from server.llm_client import chat
from server.macros import find_matching_macro, get_macro
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
    macro_name = await find_matching_macro(request.message)
    if macro_name:
        steps = get_macro(macro_name)
        await asyncio.to_thread(play_macro, steps)
        return ChatResponse(reply=f"Done -- ran '{macro_name}'.")

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
