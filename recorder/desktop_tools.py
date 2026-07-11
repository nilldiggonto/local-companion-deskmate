"""Small, individually-testable desktop primitives.

These are the agent's "eyes" (list/find/inspect) and "hands" (click/type/
open). Each does one thing and reports honestly whether it worked, so the
agent loop can observe results and adjust instead of assuming success.
"""

import os
import time

import pyautogui
import win32gui
from pywinauto import Desktop

MAX_WAIT_SECONDS = 10.0


# ---------- eyes ----------

def list_windows() -> list[str]:
    titles = []
    for w in Desktop(backend="uia").windows():
        title = w.window_text() or ""
        if title.strip():
            titles.append(title)
    return titles


def get_active_window() -> str:
    return win32gui.GetWindowText(win32gui.GetForegroundWindow()) or "(unknown)"


def find_elements(
    title_contains: str,
    name_contains: str | None = None,
    control_type: str | None = None,
    limit: int = 10,
) -> list[dict]:
    window = _find_window(title_contains)
    if window is None:
        return []
    kwargs = {"control_type": control_type} if control_type else {}
    results = []
    for el in window.descendants(**kwargs):
        name = el.window_text() or ""
        if name_contains and name_contains.lower() not in name.lower():
            continue
        if not name.strip():
            continue
        results.append(
            {"name": name, "control_type": el.element_info.control_type}
        )
        if len(results) >= limit:
            break
    return results


# ---------- hands ----------

def activate_window(title_contains: str) -> bool:
    window = _find_window(title_contains)
    if window is None:
        return False
    window.set_focus()
    return True


def click_element(
    title_contains: str,
    name: str,
    control_type: str | None = None,
    button: str = "left",
) -> bool:
    window = _find_window(title_contains)
    if window is None:
        return False
    kwargs = {"control_type": control_type} if control_type else {}
    for el in window.descendants(**kwargs):
        el_name = el.window_text() or ""
        if name.lower() in el_name.lower():
            el.click_input(button=button)
            return True
    return False


def open_url(url: str) -> None:
    """Opens a URL in the user's default browser (new tab if already open)."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    os.startfile(url)


def hotkey(keys: list[str]) -> None:
    pyautogui.hotkey(*keys)


def press(key: str) -> None:
    pyautogui.press(key)


def type_text(text: str) -> None:
    pyautogui.write(text, interval=0.02)


def wait(seconds: float) -> None:
    time.sleep(min(float(seconds), MAX_WAIT_SECONDS))


# ---------- internal ----------

def _find_window(title_contains: str):
    for w in Desktop(backend="uia").windows():
        if title_contains.lower() in (w.window_text() or "").lower():
            return w
    return None
