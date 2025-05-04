import os, logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from google import genai
import asyncio
from telethon.tl.functions.messages import ImportChatInviteRequest

API_ID   = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
SESSION  = os.environ["TG_SESSION"]
TG_TARGETS = os.getenv("TG_TARGETS", "")

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
    if "joinchat" in t or t.startswith("https://t.me/"):
        hash = t.rsplit("/", 1)[-1]
        try:
            await clientTG(ImportChatInviteRequest(hash))
        except Exception as e:
            logging.warning("Join err %s: %s", t, e)
    return await clientTG.get_entity(t)

async def main():
    clientTG = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
    await clientTG.start()

    # Parse TG_TARGETS into a list
    raw = [x.strip() for x in TG_TARGETS.split(",") if x.strip()]

    # Join (if needed) and resolve each target
    entities = []
    for t in raw:
        try:
            ent = await ensure_join(clientTG, t)
            entities.append(ent)
            logging.info("Tracking %s → %s", t, ent)
        except Exception as e:
            logging.warning("Can't track %s: %s", t, e)

    @clientTG.on(events.NewMessage(chats=entities))
    async def on_post(ev):
        if ev.is_channel:
            answer = await asyncio.wait_for(smart_reply(ev.text or ""), timeout=15)
            await clientTG.send_message(ev.chat_id, answer, comment_to=ev.id)
            logging.info("replied on %s:%s", ev.chat.title, ev.id)

    logging.info("Userbot ONLINE (Gemini‑Flash)…")
    await clientTG.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
