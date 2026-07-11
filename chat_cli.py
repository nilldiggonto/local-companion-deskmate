import httpx

BASE_URL = "http://127.0.0.1:8000"
#keep running the fastapi server in the background before running this script

def main():
    print("Chatting with your local avatar. Type 'exit' to quit.")
    suggestions = []
    with httpx.Client() as client:
        while True:
            message = input("You: ").strip()
            if message.lower() in {"exit", "quit"}:
                break
            # typing just a number picks that quick reply
            if message.isdigit() and 1 <= int(message) <= len(suggestions):
                message = suggestions[int(message) - 1]
                print(f"  (-> {message})")
            response = client.post(f"{BASE_URL}/chat", json={"message": message}, timeout=180.0)
            response.raise_for_status()
            data = response.json()
            print("Bot:", data["reply"])
            suggestions = data.get("suggestions", [])
            if suggestions:
                options = "  ".join(f"[{i + 1}] {s}" for i, s in enumerate(suggestions))
                print("     quick replies:", options)


if __name__ == "__main__":
    main()
