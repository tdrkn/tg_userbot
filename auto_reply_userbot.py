import os, logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from google import genai

API_ID   = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
SESSION  = os.environ["TG_SESSION"]
TARGET   = os.environ["TG_TARGET"]

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

clientTG = TelegramClient(StringSession(SESSION), API_ID, API_HASH)

@clientTG.on(events.NewMessage(chats=TARGET))
async def on_post(ev):
    if ev.is_channel:
        answer = await smart_reply(ev.text or "")
        await clientTG.send_message(ev.chat_id, answer, comment_to=ev.id)
        logging.info("replied on post %s", ev.id)

with clientTG:
    logging.info("Userbot ONLINE (Gemini‑Flash) …")
    clientTG.run_until_disconnected()
