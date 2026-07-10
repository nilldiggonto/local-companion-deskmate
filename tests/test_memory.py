import asyncio

from server.memory import init_db, retrieve_relevant, save_memory


async def main():
    init_db()
    await save_memory("The user's favorite color is blue.")
    results = await retrieve_relevant("What color does the user like?")
    print("retrieve_relevant() results:", results)


if __name__ == "__main__":
    asyncio.run(main())
