from pynput import keyboard, mouse

from recorder.ui_inspector import get_element_at


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
        self.events.append(
            {"action": "click", "x": x, "y": y, "button": str(button), "target": target}
        )

    def _on_press(self, key) -> None:
        try:
            self._typed_buffer += key.char
        except AttributeError:
            self._flush_typed_buffer()
            self.events.append({"action": "key", "value": str(key)})

    def _flush_typed_buffer(self) -> None:
        if self._typed_buffer:
            self.events.append({"action": "type", "value": self._typed_buffer})
            self._typed_buffer = ""
