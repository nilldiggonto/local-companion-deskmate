from pathlib import Path

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QMouseEvent,
    QMoveEvent,
    QMovie,
    QPaintEvent,
    QPainter,
    QPen,
    QRadialGradient,
)
from PyQt6.QtWidgets import QLabel, QWidget

CLICK_MOVEMENT_THRESHOLD_PX = 4

# drop an animated GIF here (transparent background, roughly square) and the
# avatar will use it automatically instead of the drawn orb
AVATAR_GIF = Path(__file__).parent / "assets" / "avatar.gif"


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
        self.resize(140, 140)
        self._drag_offset: QPoint | None = None
        self._press_global_pos: QPoint | None = None

        self._movie: QMovie | None = None
        if AVATAR_GIF.exists():
            label = QLabel(self)
            label.setGeometry(0, 0, self.width(), self.height())
            label.setScaledContents(True)
            # let clicks/drags pass through the label to this window
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self._movie = QMovie(str(AVATAR_GIF))
            label.setMovie(self._movie)
            self._movie.start()

    def paintEvent(self, event: QPaintEvent) -> None:
        if self._movie is not None:
            return  # the GIF label covers the window

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(10, 10, -10, -10)
        center = rect.center()

        # soft outer glow
        glow = QRadialGradient(float(center.x()), float(center.y()), rect.width() / 1.6)
        glow.setColorAt(0.0, QColor(0, 229, 255, 90))
        glow.setColorAt(1.0, QColor(0, 229, 255, 0))
        painter.setBrush(QBrush(glow))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(self.rect())

        # core orb with a gaming-style gradient
        orb = QRadialGradient(
            float(center.x() - rect.width() / 5),
            float(center.y() - rect.height() / 5),
            rect.width() / 1.1,
        )
        orb.setColorAt(0.0, QColor("#7df9ff"))
        orb.setColorAt(0.5, QColor("#00b3e6"))
        orb.setColorAt(1.0, QColor("#0a1a4f"))
        painter.setBrush(QBrush(orb))
        painter.drawEllipse(rect)

        # neon ring
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#00e5ff"), 3))
        painter.drawEllipse(rect)

        # two little "eyes" so it feels alive
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#0a1a4f")))
        eye_w, eye_h = rect.width() // 10, rect.height() // 5
        painter.drawRoundedRect(
            center.x() - rect.width() // 6 - eye_w // 2, center.y() - eye_h // 2,
            eye_w, eye_h, 3, 3,
        )
        painter.drawRoundedRect(
            center.x() + rect.width() // 6 - eye_w // 2, center.y() - eye_h // 2,
            eye_w, eye_h, 3, 3,
        )

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
