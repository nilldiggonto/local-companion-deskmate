import time

from recorder.input_recorder import InputRecorder
from server.macros import get_macro, list_macros, save_macro
from server.memory import init_db


def main():
    init_db()

    recorder = InputRecorder()
    print("Recording for 5 seconds -- click somewhere and type a bit...")
    recorder.start()
    time.sleep(5)
    steps = recorder.stop()

    save_macro("test_macro", steps, description="a macro recorded for testing")
    print("Saved macro. All macros:", list_macros())
    print("Loaded back:", get_macro("test_macro"))


if __name__ == "__main__":
    main()
