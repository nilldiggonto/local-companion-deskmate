import time

from recorder.input_recorder import InputRecorder


def main():
    recorder = InputRecorder()
    print("Recording for 5 seconds -- click somewhere and press a few keys...")
    recorder.start()
    time.sleep(5)
    events = recorder.stop()
    print(f"Captured {len(events)} events:")
    for event in events:
        print(event)


if __name__ == "__main__":
    main()
