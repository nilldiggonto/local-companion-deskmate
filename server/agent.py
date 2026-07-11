"""The agent loop: give the local LLM a task, let it look at the screen,
take one small action at a time, observe what happened, and either finish,
fail honestly, or pause to ask the user a question.

Every ACTION it successfully executes is collected, so a successful run can
be saved as a replayable macro ("skill") -- that's the self-learning loop:
figure it out once with help, then reuse it deterministically.
"""

import asyncio
import json

from recorder import desktop_tools
from recorder.player import play_macro, report_problems
from server.llm_client import chat
from server.macros import get_macro, list_macros

MAX_STEPS = 12

SYSTEM_PROMPT = """You are an assistant that controls a Windows desktop to complete a task for the user.

You act in small steps. Each turn, reply with EXACTLY ONE JSON object and nothing else:
{"tool": "<tool name>", "args": {...}, "why": "<one short sentence>"}

TOOLS THAT LOOK (use these first -- never assume what is on screen):
- list_windows {} -> titles of all open windows
- get_active_window {} -> title of the window the user is in right now
- find_elements {"title_contains": str, "name_contains": str optional, "control_type": str optional} -> visible elements in that window

TOOLS THAT ACT (one at a time, then observe the result):
- activate_window {"title_contains": str}
- click_element {"title_contains": str, "name": str, "control_type": str optional, "button": "left"|"right"}
- open_url {"url": str} -> opens in the default browser (new tab). PREFER THIS for anything on the web: to search YouTube use https://www.youtube.com/results?search_query=your+words -- far more reliable than clicking inside web pages.
- hotkey {"keys": ["ctrl","t"]}
- press {"key": "enter"}
- type_text {"text": str}
- wait {"seconds": number} -> give an app time to open
- run_macro {"name": str} -> replay a skill the user already taught (see KNOWN SKILLS)

TOOLS THAT END THE TURN:
- ask_user {"question": str} -> when you are unsure or missing info (which browser? which folder?), ASK instead of guessing.
- done {"summary": str} -> the task is complete
- fail {"reason": str} -> you tried and cannot complete it

RULES:
- Look before acting: check list_windows / get_active_window first.
- Web content inside browsers is mostly invisible to find_elements. Use open_url with a direct or search URL instead of clicking page content.
- If a step's OBSERVATION says it failed, try a different approach or ask_user. Never repeat the exact same failing action.
- If a skill (run_macro) reported problems, NEVER run that same skill again in this task.
- USER ANSWER messages are the user answering your question -- NEVER type their words into an application with type_text.
- After two failed attempts at the same goal, stop guessing: ask_user or fail (the user can teach you a new skill).
- Be honest: if the task is done, say done; if stuck, ask_user or fail. 'done' means it actually worked -- if it did not work, use fail. JSON only, no markdown."""


class AgentSession:
    def __init__(self, task: str):
        self.task = task
        self.messages: list[dict] = []
        self.actions: list[dict] = []  # replayable steps collected from successful actions
        self.trail: list[str] = []  # human-readable log of every attempt, for the user
        self.pending_question: str | None = None


def _extract_json(text: str) -> dict | None:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _known_skills_text() -> str:
    macros = list_macros()
    if not macros:
        return "KNOWN SKILLS: none taught yet."
    lines = [f"- {m['name']}" for m in macros]
    return "KNOWN SKILLS (usable via run_macro):\n" + "\n".join(lines)


def _execute_tool(tool: str, args: dict) -> tuple[str, dict | None]:
    """Runs one tool. Returns (observation text, replayable step or None)."""
    if tool == "list_windows":
        return "Open windows: " + "; ".join(desktop_tools.list_windows()[:20]), None
    if tool == "get_active_window":
        return f"Active window: {desktop_tools.get_active_window()}", None
    if tool == "find_elements":
        found = desktop_tools.find_elements(
            args.get("title_contains", ""),
            args.get("name_contains"),
            args.get("control_type"),
        )
        if not found:
            return "No matching elements found (window may not exist, or its contents are not exposed to automation).", None
        return "Elements: " + json.dumps(found), None
    if tool == "activate_window":
        ok = desktop_tools.activate_window(args["title_contains"])
        if ok:
            return "Window activated.", {"action": "activate_window", "title_contains": args["title_contains"]}
        return f"FAILED: no window with title containing '{args['title_contains']}'.", None
    if tool == "click_element":
        ok = desktop_tools.click_element(
            args["title_contains"],
            args["name"],
            args.get("control_type"),
            args.get("button", "left"),
        )
        if ok:
            step = {
                "action": "click_element",
                "title_contains": args["title_contains"],
                "name": args["name"],
                "control_type": args.get("control_type"),
                "button": args.get("button", "left"),
            }
            return "Clicked.", step
        return f"FAILED: could not find element '{args['name']}' in that window.", None
    if tool == "open_url":
        desktop_tools.open_url(args["url"])
        return "URL opened in default browser.", {"action": "open_url", "url": args["url"]}
    if tool == "hotkey":
        desktop_tools.hotkey(args["keys"])
        return "Hotkey pressed.", {"action": "hotkey", "keys": args["keys"]}
    if tool == "press":
        desktop_tools.press(args["key"])
        return "Key pressed.", {"action": "press", "key": args["key"]}
    if tool == "type_text":
        desktop_tools.type_text(args["text"])
        return "Text typed.", {"action": "type", "value": args["text"]}
    if tool == "wait":
        desktop_tools.wait(args.get("seconds", 1))
        return "Waited.", {"action": "wait", "seconds": min(float(args.get("seconds", 1)), 10)}
    if tool == "run_macro":
        steps = get_macro(args["name"])
        if steps is None:
            return f"FAILED: no skill named '{args['name']}'.", None
        problems = report_problems(play_macro(steps))
        if problems:
            details = "; ".join(f"step {e['index']} ({e['desc']}): {e['note']}" for e in problems)
            return f"Skill ran but had problems: {details}.", None
        return "Skill ran successfully.", {"action": "run_macro", "name": args["name"]}
    return f"FAILED: unknown tool '{tool}'.", None


async def run_agent(session: AgentSession, user_answer: str | None = None) -> dict:
    """Drives the loop until done/fail/ask_user/step-limit.
    Returns {"status": ..., "message": ..., "actions": [...]}."""
    if not session.messages:
        session.messages = [
            {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + _known_skills_text()},
            {"role": "user", "content": f"TASK: {session.task}"},
        ]
    if user_answer is not None:
        session.messages.append(
            {"role": "user", "content": f"USER ANSWER: {user_answer}"}
        )
        session.pending_question = None

    for _ in range(MAX_STEPS):
        raw = await chat(session.messages)
        decision = _extract_json(raw)
        if decision is None or "tool" not in decision:
            session.messages.append({"role": "assistant", "content": raw})
            session.messages.append(
                {"role": "user", "content": "OBSERVATION: your reply was not a single valid JSON object. Reply with JSON only."}
            )
            continue

        tool = decision["tool"]
        args = decision.get("args", {}) or {}
        print(f"[agent] {tool} {args} -- {decision.get('why', '')}")
        session.messages.append({"role": "assistant", "content": json.dumps(decision)})

        why = decision.get("why", "")

        if tool == "done":
            return {
                "status": "done",
                "message": args.get("summary", "Task complete."),
                "actions": session.actions,
                "trail": session.trail,
            }
        if tool == "fail":
            return {
                "status": "fail",
                "message": args.get("reason", "I couldn't complete that."),
                "actions": session.actions,
                "trail": session.trail,
            }
        if tool == "ask_user":
            session.pending_question = args.get("question", "Can you clarify?")
            session.trail.append(f"asked you: {session.pending_question}")
            return {
                "status": "ask_user",
                "message": session.pending_question,
                "actions": session.actions,
                "trail": session.trail,
            }

        try:
            observation, step = await asyncio.to_thread(_execute_tool, tool, args)
        except Exception as exc:
            observation, step = f"FAILED with error: {exc}", None
        print(f"[agent] -> {observation[:200]}")
        if step is not None:
            session.actions.append(step)

        outcome = observation if len(observation) <= 120 else observation[:117] + "..."
        reason = f" (because: {why})" if why else ""
        session.trail.append(f"{tool} {json.dumps(args)}{reason} -> {outcome}")

        session.messages.append({"role": "user", "content": f"OBSERVATION: {observation}"})

    return {
        "status": "fail",
        "message": f"I stopped after {MAX_STEPS} steps without finishing. Try breaking the task into smaller pieces or teach me part of it with 'watch this'.",
        "actions": session.actions,
        "trail": session.trail,
    }
