import asyncio

# Thin wrapper to keep backward compatibility with existing Docker/CMD
from tg_userbot.main import run

if __name__ == "__main__":
    asyncio.run(run())
