import html

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

PANEL_STYLE = """
QWidget#panel {
    background-color: #0d1117;
    border: 2px solid #00e5ff;
    border-radius: 12px;
}
"""

HISTORY_STYLE = """
background-color: #101a2b;
color: #d6e4ff;
border: 1px solid #1f3b57;
border-radius: 8px;
padding: 8px;
font-family: Consolas, 'Courier New', monospace;
font-size: 13px;
"""

INPUT_STYLE = """
background-color: #101a2b;
color: #e8f6ff;
border: 1px solid #00e5ff;
border-radius: 8px;
padding: 7px;
font-family: Consolas, 'Courier New', monospace;
font-size: 13px;
"""

CHIP_STYLE = """
QPushButton {
    background-color: #0d2137;
    color: #00e5ff;
    border: 1px solid #00e5ff;
    border-radius: 11px;
    padding: 4px 10px;
    font-family: Consolas, 'Courier New', monospace;
    font-size: 12px;
}
QPushButton:hover {
    background-color: #00e5ff;
    color: #0d1117;
}
"""


class ChatBubble(QWidget):
    message_submitted = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(380, 480)
        self._drag_offset: QPoint | None = None

        panel = QWidget(self)
        panel.setObjectName("panel")
        panel.setStyleSheet(PANEL_STYLE)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(panel)

        self.title_bar = QLabel(">> SELF-LEARNING BOT_")
        self.title_bar.setStyleSheet(
            "color: #00e5ff; font-family: Consolas, 'Courier New', monospace; "
            "font-size: 13px; font-weight: bold; padding: 2px; border: none;"
        )
        self.title_bar.setCursor(Qt.CursorShape.SizeAllCursor)

        self.history = QTextEdit()
        self.history.setReadOnly(True)
        self.history.setStyleSheet(HISTORY_STYLE)

        self.suggestions_row = QWidget()
        self.suggestions_row.setStyleSheet("border: none;")
        self.suggestions_layout = QHBoxLayout(self.suggestions_row)
        self.suggestions_layout.setContentsMargins(0, 0, 0, 0)
        self.suggestions_layout.setSpacing(6)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type a command...")
        self.input_field.setStyleSheet(INPUT_STYLE)
        self.input_field.returnPressed.connect(self._on_submit)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.addWidget(self.title_bar)
        layout.addWidget(self.history)
        layout.addWidget(self.suggestions_row)
        layout.addWidget(self.input_field)

    # -- dragging via the title bar ------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 40:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None

    # -- chat ----------------------------------------------------------
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
        color = "#00e5ff" if sender == "You" else "#39ff88"
        safe_text = html.escape(text).replace("\n", "<br>")
        self.history.append(f'<b style="color:{color}">{sender} &gt;</b> {safe_text}')
        self.history.verticalScrollBar().setValue(self.history.verticalScrollBar().maximum())

    def set_suggestions(self, suggestions: list[str]) -> None:
        while self.suggestions_layout.count():
            item = self.suggestions_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for text in suggestions[:4]:
            button = QPushButton(text)
            button.setStyleSheet(CHIP_STYLE)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked, t=text: self.send_message(t))
            self.suggestions_layout.addWidget(button)
        self.suggestions_layout.addStretch()
