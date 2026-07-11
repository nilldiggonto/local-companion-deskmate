from pynput import keyboard, mouse

from recorder.ui_inspector import get_element_at

OWN_UI_AUTOMATION_ID_PREFIX = "QApplication."
SILENT_MODIFIER_KEYS = {keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r}


class InputRecorder:
    def __init__(self):
        self.events: list[dict] = []
        self._mouse_listener: mouse.Listener | None = None
        self._keyboard_listener: keyboard.Listener | None = None
        self._typed_buffer = ""

    def start(self) -> None:
        self.events = []
        self._typed_buffer = ""
        self._mouse_listener = mouse.Listener(on_click=self._on_click)
        self._keyboard_listener = keyboard.Listener(on_press=self._on_press)
        self._mouse_listener.start()
        self._keyboard_listener.start()

    def stop(self) -> list[dict]:
        if self._mouse_listener:
            self._mouse_listener.stop()
        if self._keyboard_listener:
            self._keyboard_listener.stop()
        self._flush_typed_buffer()
        return self.events

    def _on_click(self, x: int, y: int, button: mouse.Button, pressed: bool) -> None:
        if not pressed:
            return
        self._flush_typed_buffer()
        try:
            target = get_element_at(x, y)
        except Exception:
            target = None
        if target and target.get("automation_id", "").startswith(OWN_UI_AUTOMATION_ID_PREFIX):
            return
        self.events.append(
            {"action": "click", "x": x, "y": y, "button": str(button), "target": target}
        )

    def _on_press(self, key) -> None:
        if key == keyboard.Key.space:
            self._typed_buffer += " "
            return
        if key in SILENT_MODIFIER_KEYS:
            return
        try:
            self._typed_buffer += key.char
        except AttributeError:
            self._flush_typed_buffer()
            self.events.append({"action": "key", "value": str(key)})

    def _flush_typed_buffer(self) -> None:
        if self._typed_buffer:
            self.events.append({"action": "type", "value": self._typed_buffer})
            self._typed_buffer = ""

    def strip_trailing_submit(self, submitted_text: str) -> None:
        self._flush_typed_buffer()
        if self.events and self.events[-1]["action"] == "key" and self.events[-1]["value"] == "Key.enter":
            self.events.pop()
        if self.events and self.events[-1]["action"] == "type" and self.events[-1]["value"] == submitted_text:
            self.events.pop()

    def add_step(self, step: dict) -> None:
        self.events.append(step)
