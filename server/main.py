import asyncio
import re
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pynput.mouse import Controller as MouseController

from recorder import desktop_tools
from recorder.input_recorder import InputRecorder
from recorder.ui_inspector import get_element_at
from recorder.player import describe_step, play_macro, report_problems
from server.agent import AgentSession, run_agent
from server.llm_client import chat
from server.macros import (
    clear_all_macros,
    delete_macro,
    get_macro,
    list_macros,
    match_macro,
    record_macro_result,
    save_macro,
)
from server.memory import (
    init_db,
    recent_conversation,
    retrieve_relevant,
    save_conversation,
    save_memory,
)
from server.models import ChatRequest, ChatResponse

WATCH_TRIGGER = "watch this"
DONE_KEYWORD = "done"
CANCEL_KEYWORD = "cancel recording"
CANCEL_TASK_KEYWORD = "cancel task"
RELEARN_PREFIX = "relearn "
USE_MACRO_PREFIX = "use macro "
FORGET_PREFIX = "forget macro "
CHECK_WINDOW_PREFIX = "check if "
CHECK_WINDOW_SUFFIX = " is open"
NAME_FILLERS = ("call this ", "call it ", "name it ", "name this ")

INTENT_PROMPT = (
    "Decide if the user's message asks you to PERFORM an action on their computer "
    "(open something, click, search the web, launch an app, etc.) or is just conversation/questions. "
    "Reply with exactly one word: task or chat."
)

# only run a macro without asking when the match is this strong
AUTO_RUN_THRESHOLD = 0.8
# below auto-run but above this: ask the user first
CONFIRM_THRESHOLD = 0.6

# messages containing these are the user teaching/correcting us --
# never hijack them into running a macro
TEACHING_HINTS = (
    "learn", "teach", "watch", "don't", "dont", "wrong", "forget",
    "no,", "not ", "stop", "cancel", "instead",
)

YES_WORDS = {"yes", "y", "yes please", "ok", "okay", "sure", "run it", "yes, run it", "do it"}

_active_recorder: InputRecorder | None = None
_pending_steps: list[dict] | None = None
_relearn_target_name: str | None = None
_agent_session: AgentSession | None = None

# context for short follow-ups ("details", "fix step 3 with ...") so the user
# never has to retype a long macro name
_last_macro: str | None = None
_last_details: str | None = None
_pending_macro_confirm: str | None = None
_last_combo: list[str] | None = None
_last_agent_actions: list[dict] | None = None
_look_pending: bool = False
_last_looked: dict | None = None
_pending_forget_all: bool = False

# undo/redo for macro changes: (name, previous_steps or None if it was new)
_undo_stack: list[tuple[str, list | None]] = []
_redo_stack: list[tuple[str, list | None]] = []

# messages matching these are commands -- they always win over a pending
# agent question (so the agent can never swallow 'details' or 'watch this')
COMMAND_PATTERNS = (
    r"^details$", r"^what happened\??$", r"^steps$", r"^show (?:steps|macro) ",
    r"^watch", r"^done\b", r"^cancel (?:recording|task)$",
    r"^(?:fix|replace) step ", r"^(?:drop|remove) step ", r"^(?:add|insert) before step ",
    r"^forget macro ", r"^relearn ", r"^combine as ", r"^use macro ", r"^check if ",
    r"^undo$", r"^redo$", r"^save skill as ", r"^look$", r"^learn click",
    r"^list macros$", r"^skills$", r"^what do you know\??$",
    r"^forget all macros$", r"^is .+ open(?:ed)?\??$", r"^help$",
)

# these commands mean the user is taking over -- drop any confused agent task
TAKEOVER_PATTERN = r"^(?:watch|relearn |forget macro |undo$|redo$)"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.exception_handler(httpx.HTTPError)
async def ollama_error_handler(request: Request, exc: httpx.HTTPError):
    """When Ollama is down or crashed, answer in plain language instead of a
    raw 500. (Returned as a normal chat reply so every client shows it.)"""
    print(f"[ollama error] {exc}")
    return JSONResponse(
        status_code=200,
        content=ChatResponse(
            reply=(
                "My brain (Ollama) isn't answering right now. Usually this means it "
                "crashed or isn't running.\n"
                "1. Quit Ollama fully (tray icon -> Quit, or end 'ollama.exe' in Task Manager)\n"
                "2. Start it again\n"
                "3. Test it: run 'ollama run qwen2.5 \"hi\"' in a terminal\n"
                "Then talk to me again!"
            )
        ).model_dump(),
    )


def _strip_trailing_submit_steps(steps: list[dict], submitted_text: str) -> list[dict]:
    if steps and steps[-1]["action"] == "key" and steps[-1]["value"] == "Key.enter":
        steps = steps[:-1]
    if steps and steps[-1]["action"] == "type" and steps[-1]["value"] == submitted_text:
        steps = steps[:-1]
    return steps


def _strip_name_fillers(text: str) -> str:
    lower = text.lower()
    for filler in NAME_FILLERS:
        if lower.startswith(filler):
            return text[len(filler):].strip()
    return text.strip()


def _extract_macro_name(message: str) -> str:
    remainder = message[len(DONE_KEYWORD):].lstrip(",").strip()
    return _strip_name_fillers(remainder)


def _format_trail(trail: list[str]) -> str:
    if not trail:
        return "I haven't tried anything yet."
    lines = [f"{i + 1}. {entry}" for i, entry in enumerate(trail)]
    return "What I tried, step by step:\n" + "\n".join(lines)


def _agent_result_to_reply(result: dict, task: str) -> ChatResponse:
    global _agent_session, _last_details, _last_agent_actions

    _last_details = _format_trail(result.get("trail", []))

    if result["status"] == "ask_user":
        return ChatResponse(reply=result["message"], suggestions=["details", "cancel task"])

    _agent_session = None

    if result["status"] == "done":
        reply = result["message"]
        actions = result["actions"]
        suggestions = ["details"]
        if actions:
            _last_agent_actions = actions
            auto_name = task[:40].strip().rstrip(".?!")
            reply += (
                "\n\nDid that actually do what you wanted? If yes, I can remember it "
                "as a skill. If not, just tell me what went wrong."
            )
            suggestions = [f"save skill as {auto_name}", "details"]
        return ChatResponse(reply=reply, suggestions=suggestions)

    return ChatResponse(
        reply=result["message"] + "\n\nWant to show me how? Say 'watch this' and I'll learn by watching.",
        suggestions=["details", "watch this"],
    )


def _format_report(report: list[dict]) -> str:
    lines = []
    for e in report:
        mark = {"ok": "OK", "problem": "PROBLEM", "not run": "SKIPPED"}[e["status"]]
        line = f"{e['index']}. [{mark}] {e['desc']}"
        if e["note"]:
            line += f" -- {e['note']}"
        lines.append(line)
    return "\n".join(lines)


def _find_macro_name(requested: str) -> str | None:
    return next(
        (m["name"] for m in list_macros() if m["name"].lower() == requested.lower().strip()),
        None,
    )


def _is_command(message: str) -> bool:
    lower = message.lower().strip()
    return any(re.match(p, lower) for p in COMMAND_PATTERNS)


def _save_macro_tracked(name: str, steps: list[dict], description: str | None = None) -> None:
    """save_macro plus an undo record of what was there before."""
    _undo_stack.append((name, get_macro(name)))
    _redo_stack.clear()
    save_macro(name, steps, description=description)


def _steps_preview(steps: list[dict], limit: int = 6) -> str:
    lines = [f"{i + 1}. {describe_step(s)}" for i, s in enumerate(steps[:limit])]
    if len(steps) > limit:
        lines.append(f"...and {len(steps) - limit} more")
    return "\n".join(lines)


def _parse_step_spec(spec: str) -> tuple[dict | None, str]:
    """Turns a user-typed step description into a replayable step.
    Returns (step, "") or (None, reason)."""
    spec = spec.strip()
    lower = spec.lower()
    if lower.startswith(CHECK_WINDOW_PREFIX) and lower.endswith(CHECK_WINDOW_SUFFIX):
        title = spec[len(CHECK_WINDOW_PREFIX):-len(CHECK_WINDOW_SUFFIX)].strip()
        return {"action": "check_window", "title_contains": title}, ""
    if lower.startswith(USE_MACRO_PREFIX):
        name = spec[len(USE_MACRO_PREFIX):].strip()
        match = _find_macro_name(name)
        if match is None:
            return None, (
                f"I have no clue how to '{name}' yet -- teach me! Say 'watch this', "
                f"show me, then 'done, call this {name}'. After that, redo this edit."
            )
        return {"action": "run_macro", "name": match}, ""
    if lower.startswith("open url "):
        return {"action": "open_url", "url": spec[len("open url "):].strip()}, ""
    if lower.startswith("type "):
        return {"action": "type", "value": spec[len("type "):]}, ""
    if lower.startswith("wait "):
        try:
            seconds = float(lower[len("wait "):].replace("seconds", "").replace("s", "").strip())
        except ValueError:
            return None, "I couldn't read the number of seconds."
        return {"action": "wait", "seconds": seconds}, ""
    return None, (
        "I understand these step kinds: 'check if <window> is open', 'use macro <name>', "
        "'open url <url>', 'type <text>', 'wait <seconds>'."
    )


def _do_show_steps(name: str) -> ChatResponse:
    global _last_macro
    _last_macro = name
    steps = get_macro(name)
    lines = [f"{i + 1}. {describe_step(s)}" for i, s in enumerate(steps)]
    return ChatResponse(
        reply=f"'{name}' does this:\n" + "\n".join(lines)
        + "\n\nTo teach me better: 'fix step N with ...', 'add before step N: ...', or 'drop step N'.",
        suggestions=[f"relearn {name}"],
    )


def _do_remove_step(name: str, n: int) -> ChatResponse:
    steps = get_macro(name)
    if not 1 <= n <= len(steps):
        return ChatResponse(reply=f"'{name}' has {len(steps)} steps -- there is no step {n}.")
    removed = steps.pop(n - 1)
    _save_macro_tracked(name, steps, description=name)
    return ChatResponse(
        reply=f"Okay, dropped step {n} ({describe_step(removed)}). '{name}' now has {len(steps)} steps.",
        suggestions=["steps", "undo"],
    )


def _do_replace_step(name: str, n: int, spec: str) -> ChatResponse:
    steps = get_macro(name)
    if not 1 <= n <= len(steps):
        return ChatResponse(reply=f"'{name}' has {len(steps)} steps -- there is no step {n}.")
    new_step, error = _parse_step_spec(spec)
    if new_step is None:
        return ChatResponse(reply=error)
    old_desc = describe_step(steps[n - 1])
    steps[n - 1] = new_step
    _save_macro_tracked(name, steps, description=name)
    return ChatResponse(
        reply=f"Learned! Step {n} is now '{describe_step(new_step)}' (was: {old_desc}).",
        suggestions=["steps", "undo"],
    )


async def _run_macro_response(macro_name: str) -> ChatResponse:
    """Runs one macro and builds the friendly summary reply."""
    global _last_macro, _last_details

    steps = get_macro(macro_name)
    _last_macro = macro_name
    if not steps:
        return ChatResponse(
            reply=f"'{macro_name}' is an empty skill -- it has no steps, so it does nothing. Best to forget it.",
            suggestions=[f"forget macro {macro_name}"],
        )
    try:
        report = await asyncio.to_thread(play_macro, steps)
    except Exception as exc:
        record_macro_result(macro_name, success=False)
        return ChatResponse(
            reply=f"Oops -- '{macro_name}' hit an error: {exc}",
            suggestions=[f"relearn {macro_name}", f"forget macro {macro_name}"],
        )

    problems = report_problems(report)
    record_macro_result(macro_name, success=not problems)
    _last_details = f"Full report for '{macro_name}':\n" + _format_report(report)

    if problems:
        problem_lines = "\n".join(
            f"- step {e['index']} ({e['desc']}): {e['note']}" for e in problems
        )
        return ChatResponse(
            reply=(
                f"I ran '{macro_name}', but {len(problems)} step(s) didn't go smoothly:\n"
                + problem_lines
                + "\n\nYou can fix just that step ('fix step "
                + str(problems[0]["index"])
                + " with ...'), teach me fresh, or make me forget it."
            ),
            suggestions=["details", "steps", f"relearn {macro_name}", f"forget macro {macro_name}"],
        )

    track_record = next((m for m in list_macros() if m["name"] == macro_name), None)
    note = ""
    if track_record and track_record["fail_count"] > 0:
        note = (
            f" (it's been shaky before: {track_record['success_count']} wins, "
            f"{track_record['fail_count']} fails)"
        )
    return ChatResponse(
        reply=f"Done! Ran '{macro_name}' -- all {len(report)} steps went fine.{note}",
        suggestions=["details"],
    )


async def _run_macro_chain(names: list[str]) -> ChatResponse:
    """Runs several small skills in order and summarizes each one."""
    global _last_macro, _last_details, _last_combo

    lines = []
    details_parts = []
    all_ok = True
    for name in names:
        report = await asyncio.to_thread(play_macro, get_macro(name))
        problems = report_problems(report)
        record_macro_result(name, success=not problems)
        details_parts.append(f"'{name}':\n" + _format_report(report))
        if problems:
            all_ok = False
            lines.append(f"- '{name}': {len(problems)} step(s) had trouble")
        else:
            lines.append(f"- '{name}': all good")

    _last_combo = names
    _last_macro = names[-1]
    _last_details = "\n\n".join(details_parts)

    reply = f"Ran your {len(names)} skills in order:\n" + "\n".join(lines)
    suggestions = ["details"]
    if all_ok:
        combo_name = " then ".join(names)[:60]
        reply += "\n\nWant me to remember this whole chain as one skill?"
        suggestions.append(f"combine as {combo_name}")
    return ChatResponse(reply=reply, suggestions=suggestions)


def _is_teaching_message(message: str) -> bool:
    lower = f" {message.lower()} "
    return any(hint in lower for hint in TEACHING_HINTS)


def _do_insert_step(name: str, n: int, spec: str) -> ChatResponse:
    steps = get_macro(name)
    if not 1 <= n <= len(steps) + 1:
        return ChatResponse(
            reply=f"'{name}' has {len(steps)} steps -- I can insert at positions 1 to {len(steps) + 1}."
        )
    new_step, error = _parse_step_spec(spec)
    if new_step is None:
        return ChatResponse(reply=error)
    steps.insert(n - 1, new_step)
    _save_macro_tracked(name, steps, description=name)
    return ChatResponse(
        reply=f"Learned! Added '{describe_step(new_step)}' as step {n}. '{name}' now has {len(steps)} steps.",
        suggestions=["steps", "undo"],
    )


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    global _active_recorder, _pending_steps, _relearn_target_name, _agent_session
    global _last_macro, _last_details, _pending_macro_confirm, _last_combo
    global _last_agent_actions, _look_pending, _last_looked, _pending_forget_all

    message = request.message.strip()

    if _agent_session is not None and message.lower() == CANCEL_TASK_KEYWORD:
        task = _agent_session.task
        _agent_session = None
        return ChatResponse(reply=f"Okay, dropped the task '{task}'.")

    if _agent_session is not None and _agent_session.pending_question is not None:
        if _is_command(message):
            # commands always win -- and teaching commands take over entirely
            if re.match(TAKEOVER_PATTERN, message.lower()):
                _agent_session = None
        else:
            task = _agent_session.task
            result = await run_agent(_agent_session, user_answer=message)
            return _agent_result_to_reply(result, task)

    if message.lower() == "undo":
        if not _undo_stack:
            return ChatResponse(reply="Nothing to undo.")
        name, previous = _undo_stack.pop()
        _redo_stack.append((name, get_macro(name)))
        if previous is None:
            delete_macro(name)
            return ChatResponse(reply=f"Undone -- I forgot '{name}' (it was newly learned).")
        save_macro(name, previous, description=name)
        return ChatResponse(reply=f"Undone -- '{name}' is back to how it was before.", suggestions=["steps"])

    if message.lower() == "redo":
        if not _redo_stack:
            return ChatResponse(reply="Nothing to redo.")
        name, redo_steps = _redo_stack.pop()
        _undo_stack.append((name, get_macro(name)))
        if redo_steps is None:
            delete_macro(name)
            return ChatResponse(reply=f"Redone -- '{name}' is forgotten again.")
        save_macro(name, redo_steps, description=name)
        return ChatResponse(reply=f"Redone -- '{name}' has the newer version again.", suggestions=["steps"])

    if _pending_forget_all:
        _pending_forget_all = False
        if message.lower() in YES_WORDS or message.lower() == "yes, forget everything":
            clear_all_macros()
            _undo_stack.clear()
            _redo_stack.clear()
            _last_macro = None
            _last_combo = None
            return ChatResponse(
                reply="Clean slate! I've forgotten every skill. Teach me fresh with 'watch this' or 'look'.",
                suggestions=["watch this", "look", "help"],
            )
        # not a yes -- fall through and treat as a normal message

    if message.lower() == "forget all macros":
        macros = list_macros()
        if not macros:
            return ChatResponse(reply="I don't know any skills yet -- nothing to forget!")
        _pending_forget_all = True
        return ChatResponse(
            reply=f"This will erase ALL {len(macros)} skills I've learned, permanently. Are you sure?",
            suggestions=["yes, forget everything", "no"],
        )

    if message.lower() in ("list macros", "skills", "what do you know", "what do you know?"):
        macros = list_macros()
        if not macros:
            return ChatResponse(
                reply="I don't know any skills yet. Teach me with 'watch this' or 'look'!",
                suggestions=["watch this", "look", "help"],
            )
        lines = []
        for m in macros:
            steps = get_macro(m["name"]) or []
            record = ""
            if m["success_count"] or m["fail_count"]:
                record = f" ({m['success_count']} wins/{m['fail_count']} fails)"
            lines.append(f"- {m['name']} [{len(steps)} steps]{record}")
        return ChatResponse(
            reply=f"I know {len(macros)} skill(s):\n" + "\n".join(lines),
            suggestions=["forget all macros"],
        )

    is_open_match = re.match(r"^is (?P<t>.+?) (?:open|opened)\??$", message, re.IGNORECASE)
    if is_open_match:
        target = is_open_match.group("t").strip()
        found = await asyncio.to_thread(desktop_tools.find_open_target, target)
        if found:
            return ChatResponse(reply=f"Yes -- I can see {found}.")
        return ChatResponse(
            reply=(
                f"I don't see '{target}' anywhere. I checked all window titles and browser tabs. "
                "Heads up: browsers only show me the ACTIVE tab's name in the window title, and "
                "background tabs only when the browser exposes them -- so I can miss things."
            ),
            suggestions=["look"],
        )

    if message.lower() == "help":
        return ChatResponse(
            reply=(
                "Here's how you teach me:\n"
                "- 'watch this' -> show me ONE small action -> 'done, call this <name>'\n"
                "- 'look' -> hover something -> 'now' -> 'learn click it'\n"
                "- '<skill> then <skill>' runs skills in a chain; 'combine as <name>' saves the chain\n"
                "- 'list macros' / 'steps' / 'details' to see what I know and did\n"
                "- 'fix step N with ...', 'drop step N', 'relearn <name>', 'undo'\n"
                "- 'is <thing> open?' -- I'll check windows and browser tabs\n"
                "- 'forget macro <name>' / 'forget all macros' to reset me"
            )
        )

    save_skill_match = re.match(r"^save skill as (?P<name>.+)$", message, re.IGNORECASE)
    if save_skill_match:
        if not _last_agent_actions:
            return ChatResponse(reply="There's no recent successful task to save.")
        skill_name = save_skill_match.group("name").strip()
        _save_macro_tracked(skill_name, _last_agent_actions, description=skill_name)
        saved = _last_agent_actions
        _last_agent_actions = None
        _last_macro = skill_name
        return ChatResponse(
            reply=f"Remembered '{skill_name}'!\n" + _steps_preview(saved),
            suggestions=["steps", "undo"],
        )

    if message.lower() == "look":
        _look_pending = True
        return ChatResponse(
            reply=(
                "Hover your mouse over the thing you want to teach me about and KEEP it "
                "there. Then type 'now' and press Enter (keyboard only -- don't move the mouse!)."
            )
        )

    if _look_pending and message.lower() == "now":
        _look_pending = False
        x, y = MouseController().position
        try:
            element = get_element_at(int(x), int(y))
        except Exception:
            element = None
        if not element or not (element.get("name") or element.get("automation_id")):
            return ChatResponse(
                reply=f"I looked at ({int(x)}, {int(y)}) but couldn't identify anything there -- that app may not expose its elements. Try another spot."
            )
        _last_looked = {"element": element, "x": int(x), "y": int(y)}
        label = element.get("name") or element.get("automation_id")
        return ChatResponse(
            reply=(
                f"I see '{label}' ({element.get('control_type', 'element')}) at ({int(x)}, {int(y)}).\n"
                "Want me to learn to click it?"
            ),
            suggestions=["learn click it", "look"],
        )

    if message.lower() in ("learn click it", "learn to click it"):
        if _last_looked is None:
            return ChatResponse(reply="I haven't looked at anything yet -- say 'look' first.")
        element = _last_looked["element"]
        label = element.get("name") or element.get("automation_id") or "element"
        skill_name = f"click {label}"[:60]
        step = {
            "action": "click",
            "x": _last_looked["x"],
            "y": _last_looked["y"],
            "button": "Button.left",
            "target": element,
        }
        _save_macro_tracked(skill_name, [step], description=skill_name)
        _last_macro = skill_name
        _last_looked = None
        return ChatResponse(
            reply=f"Learned '{skill_name}'! Chain it any time, e.g. '{skill_name} then ...'.",
            suggestions=["steps", "undo"],
        )

    if _pending_macro_confirm is not None:
        confirm_name = _pending_macro_confirm
        _pending_macro_confirm = None
        if message.lower() in YES_WORDS:
            return await _run_macro_response(confirm_name)
        # not a yes -- fall through and treat this as a brand-new message

    combine_match = re.match(r"^combine as (?P<name>.+)$", message, re.IGNORECASE)
    if combine_match:
        if not _last_combo:
            return ChatResponse(reply="There's no recent chain to combine -- run a few skills together first, like 'open chrome then new tab'.")
        combo_name = combine_match.group("name").strip()
        combo_steps = [{"action": "run_macro", "name": n} for n in _last_combo]
        _save_macro_tracked(combo_name, combo_steps, description=combo_name)
        _last_macro = combo_name
        return ChatResponse(
            reply=f"Nice -- '{combo_name}' now means: " + " -> ".join(_last_combo) + ". One skill built from smaller ones!",
            suggestions=["steps", "undo"],
        )

    if message.lower().startswith(FORGET_PREFIX):
        requested_name = message[len(FORGET_PREFIX):].strip()
        match = _find_macro_name(requested_name)
        if match and delete_macro(match):
            return ChatResponse(reply=f"Forgot the macro '{match}'.")
        return ChatResponse(reply=f"I don't have a macro called '{requested_name}'.")

    if message.lower() in ("details", "what happened", "what happened?"):
        if _last_details is None:
            return ChatResponse(reply="Nothing to detail yet -- ask me to do something first!")
        return ChatResponse(reply=_last_details)

    if message.lower() in ("steps", "show steps"):
        if _last_macro is None or _find_macro_name(_last_macro) is None:
            return ChatResponse(reply="Which one? Say 'show steps <name>'.")
        return _do_show_steps(_last_macro)

    show_match = re.match(r"^show (?:steps|macro) (?P<name>.+)$", message, re.IGNORECASE)
    if show_match:
        name = _find_macro_name(show_match.group("name"))
        if name is None:
            return ChatResponse(reply=f"I don't have a macro called '{show_match.group('name')}'.")
        return _do_show_steps(name)

    # short forms work on the macro we most recently talked about
    short_remove = re.match(r"^(?:drop|remove) step (?P<n>\d+)$", message, re.IGNORECASE)
    short_replace = re.match(r"^(?:fix|replace) step (?P<n>\d+) with (?P<spec>.+)$", message, re.IGNORECASE)
    short_insert = re.match(r"^(?:add|insert) before step (?P<n>\d+)\s*:\s*(?P<spec>.+)$", message, re.IGNORECASE)
    if (short_remove or short_replace or short_insert) and (
        _last_macro is None or _find_macro_name(_last_macro) is None
    ):
        return ChatResponse(reply="Which macro do you mean? Run or 'show steps <name>' one first.")
    if short_remove:
        return _do_remove_step(_last_macro, int(short_remove.group("n")))
    if short_replace:
        return _do_replace_step(_last_macro, int(short_replace.group("n")), short_replace.group("spec"))
    if short_insert:
        return _do_insert_step(_last_macro, int(short_insert.group("n")), short_insert.group("spec"))

    remove_match = re.match(r"^remove step (?P<n>\d+) from (?P<name>.+)$", message, re.IGNORECASE)
    if remove_match:
        name = _find_macro_name(remove_match.group("name"))
        if name is None:
            return ChatResponse(reply=f"I don't have a macro called '{remove_match.group('name')}'.")
        return _do_remove_step(name, int(remove_match.group("n")))

    replace_match = re.match(
        r"^replace step (?P<n>\d+) of (?P<name>.+?) with (?P<spec>.+)$", message, re.IGNORECASE
    )
    if replace_match:
        name = _find_macro_name(replace_match.group("name"))
        if name is None:
            return ChatResponse(reply=f"I don't have a macro called '{replace_match.group('name')}'.")
        return _do_replace_step(name, int(replace_match.group("n")), replace_match.group("spec"))

    insert_match = re.match(
        r"^insert before step (?P<n>\d+) of (?P<name>.+?)\s*:\s*(?P<spec>.+)$", message, re.IGNORECASE
    )
    if insert_match:
        name = _find_macro_name(insert_match.group("name"))
        if name is None:
            return ChatResponse(reply=f"I don't have a macro called '{insert_match.group('name')}'.")
        return _do_insert_step(name, int(insert_match.group("n")), insert_match.group("spec"))

    if message.lower().startswith(RELEARN_PREFIX):
        requested_name = message[len(RELEARN_PREFIX):].strip()
        match = next(
            (m["name"] for m in list_macros() if m["name"].lower() == requested_name.lower()),
            None,
        )
        if match is None:
            return ChatResponse(reply=f"I don't have a macro called '{requested_name}'.")
        target_name = match
        _pending_steps = None
        _relearn_target_name = target_name
        _active_recorder = InputRecorder()
        _active_recorder.start()
        return ChatResponse(
            reply=f"Relearning '{target_name}'. Perform the actions, then say: done"
        )

    if message.lower().startswith("watch"):
        _pending_steps = None
        _relearn_target_name = None
        _active_recorder = InputRecorder()
        _active_recorder.start()
        return ChatResponse(
            reply=(
                "I'm watching! Show me ONE small thing (tiny skills combine best -- "
                "one click or one action), then say: done, call this <name>"
            ),
            suggestions=["cancel recording"],
        )

    if (_active_recorder is not None or _pending_steps is not None) and message.lower() == CANCEL_KEYWORD:
        if _active_recorder is not None:
            _active_recorder.stop()
            _active_recorder = None
        _pending_steps = None
        _relearn_target_name = None
        return ChatResponse(reply="Recording cancelled.")

    if _active_recorder is not None and message.lower().startswith(USE_MACRO_PREFIX):
        _active_recorder.strip_trailing_submit(message)
        referenced_name = message[len(USE_MACRO_PREFIX):].strip()
        match = next(
            (m["name"] for m in list_macros() if m["name"].lower() == referenced_name.lower()),
            None,
        )
        if match is None:
            return ChatResponse(reply=f"I don't have a macro called '{referenced_name}' to reuse.")
        _active_recorder.add_step({"action": "run_macro", "name": match})
        return ChatResponse(reply=f"Added '{match}' as a step. Keep going, or say done.")

    if (
        _active_recorder is not None
        and message.lower().startswith(CHECK_WINDOW_PREFIX)
        and message.lower().endswith(CHECK_WINDOW_SUFFIX)
    ):
        _active_recorder.strip_trailing_submit(message)
        title_contains = message[len(CHECK_WINDOW_PREFIX):-len(CHECK_WINDOW_SUFFIX)].strip()
        _active_recorder.add_step({"action": "check_window", "title_contains": title_contains})
        return ChatResponse(
            reply=f"Added a check for a window titled like '{title_contains}'. Keep going, or say done."
        )

    if _active_recorder is not None and message.lower().startswith(DONE_KEYWORD):
        steps = _active_recorder.stop()
        _active_recorder = None
        steps = _strip_trailing_submit_steps(steps, message)

        if not steps:
            _relearn_target_name = None
            return ChatResponse(
                reply="I didn't see you do anything, so there's nothing to save. Say 'watch this' to try again.",
                suggestions=["watch this"],
            )

        if _relearn_target_name is not None:
            macro_name = _relearn_target_name
            _relearn_target_name = None
            _save_macro_tracked(macro_name, steps, description=macro_name)
            _last_macro = macro_name
            return ChatResponse(
                reply=f"Got it -- I re-learned '{macro_name}':\n" + _steps_preview(steps),
                suggestions=["steps", "undo"],
            )

        macro_name = _extract_macro_name(message)
        if not macro_name:
            _pending_steps = steps
            return ChatResponse(
                reply=(
                    f"Stopped recording. Here's what I saw:\n{_steps_preview(steps)}"
                    "\n\nWhat should I call it?"
                )
            )
        _save_macro_tracked(macro_name, steps, description=macro_name)
        _last_macro = macro_name
        tip = ""
        if len(steps) > 5:
            tip = (
                "\n\nTip: that's quite a few steps for one skill. Tiny skills combine "
                "better -- next time teach one small action, then chain them like "
                "'open chrome then new tab'."
            )
        return ChatResponse(
            reply=f"Learned '{macro_name}':\n" + _steps_preview(steps) + tip,
            suggestions=["steps", "undo"],
        )

    if _pending_steps is not None:
        macro_name = _strip_name_fillers(message)
        if not macro_name:
            return ChatResponse(reply="I still need a name for that recording.")
        _save_macro_tracked(macro_name, _pending_steps, description=macro_name)
        saved_steps = _pending_steps
        _pending_steps = None
        _last_macro = macro_name
        tip = ""
        if len(saved_steps) > 5:
            tip = (
                "\n\nTip: that's quite a few steps for one skill. Tiny skills combine "
                "better -- next time teach one small action, then chain them like "
                "'open chrome then new tab'."
            )
        return ChatResponse(
            reply=f"Learned '{macro_name}':\n" + _steps_preview(saved_steps) + tip,
            suggestions=["steps", "undo"],
        )

    # never let macro matching hijack a message where the user is
    # teaching or correcting us
    if not _is_teaching_message(message):
        # a chain like "open chrome then new tab then youtube" -- match each piece
        segments = [s.strip() for s in re.split(r"(?:,|;|\bthen\b)", message, flags=re.IGNORECASE) if s.strip()]
        if len(segments) >= 2:
            matched, unknown = [], []
            for seg in segments:
                name, score = await match_macro(seg)
                if name is not None and score >= CONFIRM_THRESHOLD:
                    matched.append(name)
                else:
                    unknown.append(seg)
            if matched and not unknown:
                return await _run_macro_chain(matched)
            if matched and unknown:
                known_list = ", ".join(f"'{n}'" for n in matched)
                unknown_list = ", ".join(f"'{u}'" for u in unknown)
                return ChatResponse(
                    reply=(
                        f"I know how to do {known_list}, but I don't know {unknown_list} yet.\n"
                        f"Teach me just that missing piece: say 'watch this', show me, then "
                        f"'done, call this <name>'. Then ask me again!"
                    ),
                    suggestions=["watch this"],
                )

        macro_name, score = await match_macro(message)
        if macro_name is not None and score >= AUTO_RUN_THRESHOLD:
            return await _run_macro_response(macro_name)
        if macro_name is not None and score >= CONFIRM_THRESHOLD:
            _pending_macro_confirm = macro_name
            return ChatResponse(
                reply=f"Just checking -- do you want me to run '{macro_name}'?",
                suggestions=["yes", "no, just chat"],
            )

    intent = await chat(
        [
            {"role": "system", "content": INTENT_PROMPT},
            {"role": "user", "content": message},
        ]
    )
    if "task" in intent.strip().lower():
        _agent_session = AgentSession(task=message)
        result = await run_agent(_agent_session)
        return _agent_result_to_reply(result, message)

    memories = await retrieve_relevant(request.message)

    system_content = (
        "You are a helpful personal desktop assistant that can also learn and "
        "perform actions on the user's computer."
    )
    if memories:
        system_content += "\nHere is what you remember about the user:\n"
        system_content += "\n".join(f"- {m}" for m in memories)

    messages = [{"role": "system", "content": system_content}]
    messages.extend(recent_conversation(limit=8))
    messages.append({"role": "user", "content": request.message})
    reply = await chat(messages)

    save_conversation("user", request.message)
    save_conversation("assistant", reply)
    await save_memory(request.message)

    return ChatResponse(reply=reply)
