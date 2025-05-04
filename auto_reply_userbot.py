from telethon import TelegramClient, events
from telethon.sessions import StringSession
import os, logging

API_ID   = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
SESSION  = os.environ["TG_SESSION"]
TARGET   = os.environ["TG_TARGET"]
REPLY    = os.getenv("TG_REPLY_TEXT", "hello world!")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)

@client.on(events.NewMessage(chats=TARGET))
async def on_post(ev):
    if ev.is_channel:
        await client.send_message(ev.chat_id, REPLY, comment_to=ev.id)
        logging.info("commented post %s", ev.id)

with client:
    logging.info("Userbot ONLINE, waiting for posts…")
    client.run_until_disconnected()
