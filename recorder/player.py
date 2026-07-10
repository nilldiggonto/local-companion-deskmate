import time

import pyautogui
from pywinauto import Desktop

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


def _play_click(step: dict) -> None:
    element = _find_element(step.get("target"))
    if element is not None:
        element.click_input()
        return
    pyautogui.click(step["x"], step["y"])


def _play_type(step: dict) -> None:
    pyautogui.write(step["value"], interval=0.02)


def _play_key(step: dict) -> None:
    key_name = SPECIAL_KEY_MAP.get(step["value"])
    if key_name:
        pyautogui.press(key_name)


def play_macro(steps: list[dict], delay: float = 0.3) -> None:
    for step in steps:
        action = step["action"]
        if action == "click":
            _play_click(step)
        elif action == "type":
            _play_type(step)
        elif action == "key":
            _play_key(step)
        time.sleep(delay)
