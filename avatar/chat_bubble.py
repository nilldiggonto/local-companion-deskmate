import html

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class ChatBubble(QWidget):
    message_submitted = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.resize(360, 460)
        self.setStyleSheet("background-color: #f2f2f2; border-radius: 10px;")

        self.history = QTextEdit()
        self.history.setReadOnly(True)
        self.history.setStyleSheet(
            "background-color: white; color: black; border-radius: 8px; "
            "padding: 8px; font-size: 13px;"
        )

        self.suggestions_row = QWidget()
        self.suggestions_layout = QHBoxLayout(self.suggestions_row)
        self.suggestions_layout.setContentsMargins(0, 0, 0, 0)
        self.suggestions_layout.setSpacing(6)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type a message...")
        self.input_field.setStyleSheet(
            "background-color: white; color: black; border-radius: 6px; padding: 6px;"
        )
        self.input_field.returnPressed.connect(self._on_submit)

        layout = QVBoxLayout(self)
        layout.addWidget(self.history)
        layout.addWidget(self.suggestions_row)
        layout.addWidget(self.input_field)

    def _on_submit(self) -> None:
        text = self.input_field.text().strip()
        if not text:
            return
        self.input_field.clear()
        self.send_message(text)

    def send_message(self, text: str) -> None:
        self.set_suggestions([])
        self.add_message("You", text)
        self.message_submitted.emit(text)

    def add_message(self, sender: str, text: str) -> None:
        color = "#1565c0" if sender == "You" else "#2e7d32"
        safe_text = html.escape(text).replace("\n", "<br>")
        self.history.append(f'<b style="color:{color}">{sender}:</b> {safe_text}')
        self.history.verticalScrollBar().setValue(self.history.verticalScrollBar().maximum())

    def set_suggestions(self, suggestions: list[str]) -> None:
        while self.suggestions_layout.count():
            item = self.suggestions_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for text in suggestions[:4]:
            button = QPushButton(text)
            button.setStyleSheet(
                "background-color: #e3f2fd; color: #1565c0; border: 1px solid #90caf9; "
                "border-radius: 10px; padding: 4px 10px; font-size: 12px;"
            )
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked, t=text: self.send_message(t))
            self.suggestions_layout.addWidget(button)
        self.suggestions_layout.addStretch()
