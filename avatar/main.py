import sys

from PyQt6.QtWidgets import QApplication

from avatar.avatar_window import AvatarWindow
from avatar.chat_bubble import ChatBubble
from avatar.chat_worker import ChatWorker
from avatar.server_launcher import start_server
from avatar.tray import AvatarTrayIcon


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    server_process = start_server()
    app.aboutToQuit.connect(server_process.terminate)

    avatar = AvatarWindow()
    bubble = ChatBubble()
    active_workers = []

    def toggle_bubble():
        if bubble.isVisible():
            bubble.hide()
        else:
            bubble.move(avatar.x() + avatar.width(), avatar.y())
            bubble.show()

    def handle_message(text: str):
        bubble.input_field.setEnabled(False)
        worker = ChatWorker(text)
        active_workers.append(worker)

        def on_reply(reply: str):
            bubble.add_message("Bot", reply)
            bubble.input_field.setEnabled(True)

        def on_error(msg: str):
            bubble.add_message("Bot", f"Error: {msg}")
            bubble.input_field.setEnabled(True)

        worker.reply_ready.connect(on_reply)
        worker.error.connect(on_error)
        worker.finished.connect(lambda: active_workers.remove(worker))
        worker.start()

    avatar.clicked.connect(toggle_bubble)
    bubble.message_submitted.connect(handle_message)

    tray = AvatarTrayIcon(avatar)
    tray.show()

    avatar.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
