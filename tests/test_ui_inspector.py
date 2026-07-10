import time

from pynput.mouse import Controller

from recorder.ui_inspector import get_element_at


def main():
    print("Hover your mouse over any UI element. Capturing in 3 seconds...")
    time.sleep(3)
    x, y = Controller().position
    info = get_element_at(x, y)
    print(f"Element at ({x}, {y}):")
    print(info)


if __name__ == "__main__":
    main()
