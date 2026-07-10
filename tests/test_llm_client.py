import asyncio

from server.llm_client import chat, embed


async def main():
    reply = await chat([{"role": "user", "content": "Say hello in one short sentence."}])
    print("chat() reply:", reply)

    vector = await embed("hello world")
    print("embed() vector length:", len(vector))


if __name__ == "__main__":
    asyncio.run(main())
