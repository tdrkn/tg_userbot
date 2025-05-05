import os, logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from google import genai
import asyncio
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors.rpcerrorlist import FloodWaitError
import csv
import aiofiles


API_ID   = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
SESSION  = os.environ["TG_SESSION"]
# TG_TARGETS = os.getenv("TG_TARGETS", "")

GEMINI_KEY   = os.getenv("GEMINI_KEY")
MODEL_NAME   = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")   # flash 2.0
PROMPT_TPL   = os.getenv("GEMINI_PROMPT", "{text}")
FALLBACK     = os.getenv("TG_REPLY_TEXT", "🤖 …")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

# ── Gemini init ───────────────────────────────────────
if GEMINI_KEY:
    client = genai.Client(api_key=GEMINI_KEY)
else:
    client = None
# ------------------------------------------------------

async def smart_reply(post_text: str) -> str:
    if not client:
        return FALLBACK
    prompt = PROMPT_TPL.replace("{text}", post_text[:2000])
    try:
        resp = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt
        )
        return resp.text.strip()
    except Exception as e:
        logging.warning("Gemini err: %s", e)
        return FALLBACK

async def ensure_join(clientTG, t: str):
    """
    Resolve a chat from username or invite link, and join the channel if not already a member.
    """
    # Clean trailing punctuation/invisible chars
    target = t.strip().rstrip(':\u200b\u200c\u200d')

    entity = None
    # First, handle invite links
    if "joinchat" in target or target.startswith("https://t.me/"):
        hash = target.rsplit("/", 1)[-1].lstrip("+")
        try:
            await clientTG(ImportChatInviteRequest(hash))
            entity = await clientTG.get_entity(target)
        except Exception as e:
            logging.warning("Invite join failed for %s: %s", target, e)

    # Fallback: resolve by username or ID
    if not entity:
        try:
            entity = await clientTG.get_entity(target)
        except Exception as e:
            logging.warning("Cannot resolve entity for %s: %s", target, e)
            return None

    # Disabled automatic join attempt to prevent flood waits
    pass

    return entity

async def load_targets_from_csv(path="channels.csv") -> list[str]:
    async with aiofiles.open(path, mode="r") as f:
        text = await f.read()
    return [row[0].strip() for row in csv.reader(text.splitlines()) if row and row[0].strip()]

async def main():
    clientTG = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
    await clientTG.start()

    # Map of target string to entity ID
    target_to_id: dict[str, int] = {}
    # Initial load from CSV
    csv_targets = await load_targets_from_csv()
    for t in csv_targets:
        ent = await ensure_join(clientTG, t)
        if ent:
            target_to_id[t] = ent.id
            logging.info("Tracking %s", ent.title or ent.username or ent.id)
        else:
            logging.warning("Skipped tracking %s", t)
    tracked_ids = set(target_to_id.values())

    # Background task: refresh channels every 5 minutes
    async def refresher():
        nonlocal target_to_id, tracked_ids
        while True:
            csv_targets = await load_targets_from_csv()
            # Add new targets
            for t in csv_targets:
                if t not in target_to_id:
                    ent = await ensure_join(clientTG, t)
                    if ent:
                        target_to_id[t] = ent.id
                        logging.info("Tracking %s", ent.title or ent.username or ent.id)
                    else:
                        logging.warning("Skipped tracking %s", t)
            # Remove deleted targets
            removed = set(target_to_id) - set(csv_targets)
            for t in removed:
                removed_id = target_to_id.pop(t)
                logging.info("Stopped tracking %s", t)
            tracked_ids = set(target_to_id.values())
            await asyncio.sleep(300)
    asyncio.create_task(refresher())

    @clientTG.on(events.NewMessage)
    async def on_post(ev):
        # logging.info("⚡ Got message in chat: %s (%s) — text: %r", getattr(ev.chat, 'title', 'unknown'), ev.chat_id, ev.text)
        # logging.info("🔍 Current tracked_ids: %s", tracked_ids)

        if ev.is_channel and ev.chat.id in tracked_ids:
            logging.info("✅ Message matched tracked channel: %s", ev.chat.title)
            answer = await asyncio.wait_for(smart_reply(ev.text or ""), timeout=15)
            await clientTG.send_message(ev.chat_id, answer, comment_to=ev.id)
            logging.info("💬 Replied in %s to message %s", ev.chat.title, ev.id)
        else:
            # logging.info("⛔ Ignored message from: %s (%s)", getattr(ev.chat, 'title', 'unknown'), ev.chat_id)
            pass

    logging.info("Userbot ONLINE (Gemini‑Flash)…")
    await clientTG.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
