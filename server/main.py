import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from recorder.input_recorder import InputRecorder
from recorder.player import play_macro
from server.llm_client import chat
from server.macros import find_matching_macro, get_macro, save_macro
from server.memory import init_db, retrieve_relevant, save_memory
from server.models import ChatRequest, ChatResponse

WATCH_TRIGGER = "watch this"
DONE_KEYWORD = "done"
CANCEL_KEYWORD = "cancel recording"
NAME_FILLERS = ("call this ", "call it ", "name it ", "name this ")

_active_recorder: InputRecorder | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


def _strip_trailing_submit_steps(steps: list[dict], submitted_text: str) -> list[dict]:
    if steps and steps[-1]["action"] == "key" and steps[-1]["value"] == "Key.enter":
        steps = steps[:-1]
    if steps and steps[-1]["action"] == "type" and steps[-1]["value"] == submitted_text:
        steps = steps[:-1]
    return steps


def _extract_macro_name(message: str) -> str:
    remainder = message[len(DONE_KEYWORD):].lstrip(",").strip()
    lower = remainder.lower()
    for filler in NAME_FILLERS:
        if lower.startswith(filler):
            remainder = remainder[len(filler):].strip()
            break
    return remainder


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    global _active_recorder

    message = request.message.strip()

    if message.lower() == WATCH_TRIGGER:
        _active_recorder = InputRecorder()
        _active_recorder.start()
        return ChatResponse(
            reply="Recording started. Perform the actions, then say: done, call this <name>"
        )

    if _active_recorder is not None and message.lower() == CANCEL_KEYWORD:
        _active_recorder.stop()
        _active_recorder = None
        return ChatResponse(reply="Recording cancelled.")

    if _active_recorder is not None and message.lower().startswith(DONE_KEYWORD):
        steps = _active_recorder.stop()
        _active_recorder = None
        steps = _strip_trailing_submit_steps(steps, message)
        macro_name = _extract_macro_name(message)
        if not macro_name:
            return ChatResponse(
                reply="Stopped recording, but I need a name -- try 'done, call this <name>'."
            )
        save_macro(macro_name, steps, description=macro_name)
        return ChatResponse(reply=f"Saved macro '{macro_name}' ({len(steps)} steps).")

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
