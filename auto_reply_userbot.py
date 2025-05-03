from telethon import TelegramClient, events
from telethon.sessions import StringSession
import os, logging

API_ID   = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")
TARGET   = os.getenv("TG_TARGET")        # пишем @durov чтобы свести его с ума 
REPLY    = os.getenv("TG_REPLY_TEXT")
SESSION  = os.getenv("TG_SESSION")       # сессия

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)

@client.on(events.NewMessage(chats=TARGET))
async def on_post(ev):
    if ev.is_channel and not ev.is_group:
        await client.send_message(ev.chat_id, REPLY, comment_to=ev.id)
        logging.info("Replied to post %s", ev.id)

with client:
    logging.info("Userbot online. Waiting for posts…")
    client.run_until_disconnected()
