import httpx
from PyQt6.QtCore import QThread, pyqtSignal

BASE_URL = "http://127.0.0.1:8000"


class ChatWorker(QThread):
    reply_ready = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, message: str, parent=None):
        super().__init__(parent)
        self.message = message

    def run(self) -> None:
        try:
            with httpx.Client() as client:
                response = client.post(
                    f"{BASE_URL}/chat", json={"message": self.message}, timeout=180.0
                )
                response.raise_for_status()
                self.reply_ready.emit(response.json()["reply"])
        except httpx.HTTPError as exc:
            self.error.emit(str(exc))
