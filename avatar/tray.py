from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget


def _make_icon() -> QIcon:
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#4A90D9"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(2, 2, 28, 28)
    painter.end()
    return QIcon(pixmap)


class AvatarTrayIcon(QSystemTrayIcon):
    def __init__(self, avatar: QWidget, parent=None):
        super().__init__(_make_icon(), parent)
        self.setToolTip("Self-Learning Avatar")

        menu = QMenu()

        show_action = QAction("Show", menu)
        show_action.triggered.connect(avatar.show)
        menu.addAction(show_action)

        hide_action = QAction("Hide", menu)
        hide_action.triggered.connect(avatar.hide)
        menu.addAction(hide_action)

        menu.addSeparator()

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)
