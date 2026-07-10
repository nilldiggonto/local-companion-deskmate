from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QMouseEvent, QMoveEvent, QPaintEvent, QPainter
from PyQt6.QtWidgets import QWidget

CLICK_MOVEMENT_THRESHOLD_PX = 4


class AvatarWindow(QWidget):
    clicked = pyqtSignal()
    moved = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(120, 120)
        self._drag_offset: QPoint | None = None
        self._press_global_pos: QPoint | None = None

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(QColor("#4A90D9")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(self.rect().adjusted(4, 4, -4, -4))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            self._press_global_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._press_global_pos is not None:
            moved_by = event.globalPosition().toPoint() - self._press_global_pos
            if abs(moved_by.x()) < CLICK_MOVEMENT_THRESHOLD_PX and abs(moved_by.y()) < CLICK_MOVEMENT_THRESHOLD_PX:
                self.clicked.emit()
        self._drag_offset = None
        self._press_global_pos = None

    def moveEvent(self, event: QMoveEvent) -> None:
        super().moveEvent(event)
        self.moved.emit()
