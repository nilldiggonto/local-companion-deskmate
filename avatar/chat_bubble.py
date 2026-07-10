from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLineEdit, QTextEdit, QVBoxLayout, QWidget


class ChatBubble(QWidget):
    message_submitted = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.resize(320, 420)
        self.setStyleSheet("background-color: #f2f2f2; border-radius: 10px;")

        self.history = QTextEdit()
        self.history.setReadOnly(True)
        self.history.setStyleSheet(
            "background-color: white; color: black; border-radius: 8px; padding: 8px;"
        )

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type a message...")
        self.input_field.setStyleSheet(
            "background-color: white; color: black; border-radius: 6px; padding: 6px;"
        )
        self.input_field.returnPressed.connect(self._on_submit)

        layout = QVBoxLayout(self)
        layout.addWidget(self.history)
        layout.addWidget(self.input_field)

    def _on_submit(self) -> None:
        text = self.input_field.text().strip()
        if not text:
            return
        self.input_field.clear()
        self.add_message("You", text)
        self.message_submitted.emit(text)

    def add_message(self, sender: str, text: str) -> None:
        self.history.append(f"<b>{sender}:</b> {text}")
        self.history.verticalScrollBar().setValue(self.history.verticalScrollBar().maximum())
