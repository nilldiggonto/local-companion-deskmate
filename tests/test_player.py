import time

from recorder.player import play_macro
from server.macros import get_macro


def main():
    steps = get_macro("test_macro")
    if steps is None:
        print("No macro named 'test_macro' found. Run tests/test_macros.py first.")
        return

    print("Replaying 'test_macro' in 3 seconds. Hands off the keyboard/mouse...")
    time.sleep(3)
    play_macro(steps)
    print("Done.")


if __name__ == "__main__":
    main()
