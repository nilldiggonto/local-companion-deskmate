import httpx

BASE_URL = "http://127.0.0.1:8000"
#keep running the fastapi server in the background before running this script

def main():
    print("Chatting with your local avatar. Type 'exit' to quit.")
    with httpx.Client() as client:
        while True:
            message = input("You: ").strip()
            if message.lower() in {"exit", "quit"}:
                break
            response = client.post(f"{BASE_URL}/chat", json={"message": message}, timeout=180.0)
            response.raise_for_status()
            print("Bot:", response.json()["reply"])


if __name__ == "__main__":
    main()
