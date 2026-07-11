from server.macros import clear_all_macros, list_macros
from server.memory import init_db


def main():
    init_db()
    clear_all_macros()
    print("All macros cleared. Remaining:", list_macros())


if __name__ == "__main__":
    main()
