import time

import pyautogui
from pywinauto import Desktop

from recorder import desktop_tools
from server.macros import get_macro

SPECIAL_KEY_MAP = {
    "Key.enter": "enter",
    "Key.tab": "tab",
    "Key.esc": "esc",
    "Key.space": "space",
    "Key.backspace": "backspace",
    "Key.alt_l": "alt",
    "Key.alt_r": "alt",
    "Key.ctrl_l": "ctrl",
    "Key.ctrl_r": "ctrl",
    "Key.shift": "shift",
}


def _find_element(target: dict | None):
    if not target or not target.get("automation_id"):
        return None
    try:
        return Desktop(backend="uia").window(
            auto_id=target["automation_id"], top_level_only=False
        ).wrapper_object()
    except Exception:
        return None


def _play_click(step: dict) -> bool:
    """Performs the click. Returns True if this step's element reference is
    broken -- it had an automation_id recorded, but that element can no
    longer be found (as opposed to never having one, which is expected for
    apps like Electron/browsers and isn't a "failure")."""
    target = step.get("target")
    button = "right" if "right" in step.get("button", "").lower() else "left"
    element = _find_element(target)
    if element is not None:
        print(f"  click ({button}): found element via pywinauto ({target})")
        element.click_input(button=button)
        return False
    print(f"  click ({button}): no element match, falling back to coordinates ({step['x']}, {step['y']})")
    pyautogui.click(step["x"], step["y"], button=button)
    return bool(target and target.get("automation_id"))


def _play_type(step: dict) -> None:
    print(f"  type: {step['value']!r} (clearing existing field content first)")
    pyautogui.hotkey("ctrl", "a")
    pyautogui.write(step["value"], interval=0.02)


def _play_key(step: dict) -> None:
    key_name = SPECIAL_KEY_MAP.get(step["value"])
    if key_name:
        print(f"  key: {step['value']} -> {key_name}")
        pyautogui.press(key_name)
    else:
        print(f"  key: {step['value']} has no mapping, skipped")


def _check_window(title_contains: str) -> bool:
    try:
        windows = Desktop(backend="uia").windows()
        return any(title_contains.lower() in (w.window_text() or "").lower() for w in windows)
    except Exception:
        return False


def describe_step(step: dict) -> str:
    """One human-readable line per step, so the user can point at a step
    number in chat and correct it."""
    action = step["action"]
    if action == "click":
        target = step.get("target") or {}
        label = target.get("name") or target.get("automation_id") or ""
        button = "right-click" if "right" in step.get("button", "").lower() else "click"
        if label:
            return f"{button} on '{label}' ({target.get('control_type', 'element')})"
        return f"{button} at screen position ({step['x']}, {step['y']})"
    if action == "type":
        return f"type '{step['value']}'"
    if action == "key":
        return f"press {step['value'].replace('Key.', '')}"
    if action == "run_macro":
        return f"run skill '{step['name']}'"
    if action == "check_window":
        return f"check that a window titled like '{step['title_contains']}' is open"
    if action == "activate_window":
        return f"switch to the window titled like '{step['title_contains']}'"
    if action == "click_element":
        return f"click '{step['name']}' inside the '{step['title_contains']}' window"
    if action == "open_url":
        return f"open {step['url']} in the browser"
    if action == "hotkey":
        return "press " + "+".join(step["keys"])
    if action == "press":
        return f"press {step['key']}"
    if action == "wait":
        return f"wait {step['seconds']}s"
    return action


def play_macro(steps: list[dict], delay: float = 0.5) -> list[dict]:
    """Executes the steps and returns a full report: one entry per step with
    {index, desc, status ('ok'/'problem'/'not run'), note}."""
    report = []
    stopped = False
    for i, step in enumerate(steps):
        entry = {"index": i + 1, "desc": describe_step(step), "status": "ok", "note": ""}
        if stopped:
            entry["status"] = "not run"
            entry["note"] = "skipped because an earlier step failed"
            report.append(entry)
            continue

        print(f"Step {i + 1}/{len(steps)}: {entry['desc']}")
        action = step["action"]
        try:
            if action == "click":
                broken = _play_click(step)
                if broken:
                    entry["status"] = "problem"
                    entry["note"] = "couldn't find this element anymore, clicked its old screen position instead"
            elif action == "type":
                _play_type(step)
            elif action == "key":
                _play_key(step)
            elif action == "run_macro":
                sub_name = step["name"]
                sub_steps = get_macro(sub_name)
                if sub_steps is None:
                    entry["status"] = "problem"
                    entry["note"] = f"the skill '{sub_name}' no longer exists"
                else:
                    print(f"  running sub-macro '{sub_name}'")
                    sub_report = play_macro(sub_steps, delay)
                    sub_problems = [e for e in sub_report if e["status"] == "problem"]
                    if sub_problems:
                        entry["status"] = "problem"
                        entry["note"] = "inside it: " + "; ".join(
                            f"its step {e['index']} ({e['desc']}) -- {e['note']}" for e in sub_problems
                        )
            elif action == "check_window":
                title = step["title_contains"]
                if not _check_window(title):
                    entry["status"] = "problem"
                    entry["note"] = f"no window titled like '{title}' is open, so I stopped here"
                    stopped = True
            elif action == "activate_window":
                if not desktop_tools.activate_window(step["title_contains"]):
                    entry["status"] = "problem"
                    entry["note"] = "that window isn't open, so I stopped here"
                    stopped = True
            elif action == "click_element":
                ok = desktop_tools.click_element(
                    step["title_contains"],
                    step["name"],
                    step.get("control_type"),
                    step.get("button", "left"),
                )
                if not ok:
                    entry["status"] = "problem"
                    entry["note"] = "couldn't find that element in that window"
            elif action == "open_url":
                desktop_tools.open_url(step["url"])
            elif action == "hotkey":
                desktop_tools.hotkey(step["keys"])
            elif action == "press":
                desktop_tools.press(step["key"])
            elif action == "wait":
                desktop_tools.wait(step["seconds"])
        except pyautogui.FailSafeException:
            entry["status"] = "problem"
            entry["note"] = "aborted -- the click landed at a screen corner (safety stop)"
            stopped = True
        except Exception as exc:
            entry["status"] = "problem"
            entry["note"] = f"unexpected error: {exc}"
            stopped = True

        if entry["note"]:
            print(f"  -> {entry['status']}: {entry['note']}")
        report.append(entry)
        time.sleep(delay)
    return report


def report_problems(report: list[dict]) -> list[dict]:
    return [e for e in report if e["status"] == "problem"]
