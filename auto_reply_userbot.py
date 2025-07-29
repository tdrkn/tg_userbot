import os, logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession
import google.generativeai as genai
import asyncio
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors.rpcerrorlist import FloodWaitError, UserAlreadyParticipantError
import csv
import aiofiles
from dotenv import load_dotenv
import random
from datetime import datetime, timezone

load_dotenv()


API_ID   = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
SESSION  = os.environ["TG_SESSION"]
# TG_TARGETS = os.getenv("TG_TARGETS", "")

GEMINI_KEY   = os.getenv("GEMINI_KEY")
MODEL_NAME   = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")   # flash 2.0
PROMPT_TPL   = os.getenv("GEMINI_PROMPT", "{text}")
PROMPT_IMAGE_TPL = os.getenv("GEMINI_PROMPT_IMAGE", "Опиши это изображение и прокомментируй его.")
FALLBACK     = os.getenv("TG_REPLY_TEXT", "🤖 …")
REPLY_CHANCE = float(os.getenv("REPLY_CHANCE", "1.0"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

# Set to keep track of processed album IDs to avoid duplicate replies
processed_albums = set()

# ── Gemini init ───────────────────────────────────────
gemini_model = None
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    gemini_model = genai.GenerativeModel(MODEL_NAME)
    logging.info("Gemini model '%s' initialized.", MODEL_NAME)
else:
    logging.warning("GEMINI_KEY is not set. AI features will be disabled.")
# ------------------------------------------------------

async def smart_reply(post_text: str, prompt_template: str, image_data: bytes = None, image_mime: str = None) -> str:
    if not gemini_model:
        logging.warning("Attempted to use smart_reply, but Gemini model is not initialized (check GEMINI_KEY).")
        return FALLBACK

    # Create content parts
    content_parts = []

    # Add image if provided
    if image_data and image_mime:
        import PIL.Image
        import io

        # Convert bytes to PIL Image for google-generativeai
        image = PIL.Image.open(io.BytesIO(image_data))
        content_parts.append(image)
        logging.info("📷 Added image to prompt (size: %d bytes, type: %s)", len(image_data), image_mime)

    # Add text prompt
    if post_text:
        # If there's an image, combine the image prompt with the text prompt
        if image_data:
            prompt = f"{PROMPT_IMAGE_TPL}\n\n{prompt_template.replace('{text}', post_text[:2000])}"
        else:
            prompt = prompt_template.replace("{text}", post_text[:2000])
    else:
        # If no text but image exists, use a special prompt for image-only posts
        prompt = PROMPT_IMAGE_TPL if image_data else ""

    if not prompt and not image_data:
        logging.info("Post has no text or image, skipping reply.")
        return ""

    content_parts.append(prompt)

    logging.info("➡️ Sending prompt to Gemini: \"%s...\"", prompt[:100])

    try:
        # Use the generate_content method with content parts
        resp = await gemini_model.generate_content_async(content_parts)

        # Log safety feedback from Gemini
        if resp.prompt_feedback.block_reason:
            logging.warning("Gemini prompt was blocked. Reason: %s", resp.prompt_feedback.block_reason.name)
            return FALLBACK

        if not resp.parts:
            logging.warning("Gemini response is empty (no parts). Full feedback: %s", resp.prompt_feedback)
            return FALLBACK

        # Normalize whitespace
        clean_text = ' '.join(resp.text.split())
        logging.info("⬅️ Received response from Gemini: \"%s...\"", clean_text[:50])
        return clean_text
    except Exception as e:
        logging.error("An unexpected error occurred with Gemini API: %s", e, exc_info=True)
        return FALLBACK

async def extract_image_from_message(message) -> tuple[bytes, str]:
    """
    Extract image data from a Telegram message.
    Returns (image_bytes, mime_type) or (None, None) if no image found.
    """
    try:
        if not message.photo:
            return None, None

        # Download the photo to memory
        image_bytes = await message.download_media(file=bytes)

        if not image_bytes:
            return None, None

        # Determine MIME type based on file size and common formats
        # Most Telegram photos are JPEG
        mime_type = "image/jpeg"

        # Check file size limit (Gemini has 20MB limit for entire request)
        if len(image_bytes) > 15 * 1024 * 1024:  # 15MB to be safe
            logging.warning("Image too large (%d bytes), skipping", len(image_bytes))
            return None, None

        logging.info("📥 Downloaded image: %d bytes", len(image_bytes))
        return image_bytes, mime_type

    except Exception as e:
        logging.warning("Failed to extract image from message: %s", e)
        return None, None

async def test_gemini():
    if not gemini_model:
        logging.warning("Skipping Gemini test because model is not initialized.")
        return
    try:
        logging.info("Performing a test query to Gemini...")
        test_prompt = "Hello! This is a test prompt. If you see this, please respond with just the word 'OK'."
        response = await gemini_model.generate_content_async(test_prompt)
        # Simple check for the word OK in the response
        if 'OK' in response.text:
            logging.info("✅ Gemini test successful.")
        else:
            logging.warning("Gemini test failed. Received an unexpected response: %s", response.text.strip())
    except Exception as e:
        logging.error("Gemini test failed with an error: %s", e, exc_info=True)


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

    # Join the channel if we are not already a member
    try:
        await clientTG(JoinChannelRequest(entity))
    except UserAlreadyParticipantError:
        # Already in the channel, it's fine
        pass
    except FloodWaitError as e:
        logging.warning("Flood wait for %s seconds when joining %s", e.seconds, target)
        await asyncio.sleep(e.seconds + 5) # Wait a bit longer
    except Exception as e:
        logging.error("Failed to join %s: %s", target, e)
        return None

    return entity

async def load_targets_from_csv(path="channels.csv") -> list[str]:
    try:
        async with aiofiles.open(path, mode="r", encoding="utf-8") as f:
            text = await f.read()
        return [row[0].strip() for row in csv.reader(text.splitlines()) if row and row[0].strip()]
    except FileNotFoundError:
        logging.warning("'%s' not found. No channels will be tracked.", path)
        return []
    except Exception as e:
        logging.error("Failed to read or parse '%s': %s", path, e)
        return []


async def main():
    # Get the current time in UTC when the bot starts.
    # This is crucial to ignore messages that arrived while the bot was offline.
    start_time = datetime.now(timezone.utc)
    logging.info("Bot started at %s. Ignoring messages older than this.", start_time)

    clientTG = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
    await clientTG.start()

    # Test Gemini connection on startup
    await test_gemini()

    # Map of target string to entity ID
    target_to_id: dict[str, int] = {}
    # Initial load from CSV
    logging.info("Starting initial channel setup...")
    csv_targets = await load_targets_from_csv()
    for t in csv_targets:
        ent = await ensure_join(clientTG, t)
        if ent:
            target_to_id[t] = ent.id
            logging.info("Tracking %s", ent.title or ent.username or ent.id)
        else:
            logging.warning("Skipped tracking %s", t)

        # Human-like delay after each join attempt
        delay = random.uniform(5, 15)
        logging.info("Waiting for %.1f seconds before next action...", delay)
        await asyncio.sleep(delay)

    logging.info("Initial channel setup complete.")
    tracked_ids = set(target_to_id.values())

    # Background task: refresh channels every 5 minutes
    async def refresher():
        nonlocal target_to_id, tracked_ids
        while True:
            await asyncio.sleep(300) # Refresh first, then sleep
            logging.info("Refreshing channel list from CSV...")
            csv_targets = await load_targets_from_csv()
            if not csv_targets:
                logging.warning("CSV is empty or could not be read. No changes to tracked channels.")
                continue

            # Add new targets
            current_targets = set(target_to_id.keys())
            new_targets = set(csv_targets) - current_targets

            for t in new_targets:
                ent = await ensure_join(clientTG, t)
                if ent:
                    target_to_id[t] = ent.id
                    logging.info("Started tracking new channel: %s", ent.title or ent.username or ent.id)
                else:
                    logging.warning("Skipped tracking new target: %s", t)

                # Human-like delay after each join attempt
                delay = random.uniform(5, 15)
                logging.info("Waiting for %.1f seconds before next action...", delay)
                await asyncio.sleep(delay)

            # Remove deleted targets
            removed_targets = current_targets - set(csv_targets)
            for t in removed_targets:
                target_to_id.pop(t)
                logging.info("Stopped tracking channel: %s", t)

            tracked_ids = set(target_to_id.values())

    asyncio.create_task(refresher())

    @clientTG.on(events.NewMessage)
    async def on_post(ev):
        # Ignore messages that are older than the bot's start time to prevent replying to history.
        if ev.date < start_time:
            return

        # --- Album Handling ---
        album_id = ev.grouped_id
        if album_id:
            if album_id in processed_albums:
                # If we are already processing this album, ignore the message.
                logging.info("Ignoring duplicate message from album ID: %s", album_id)
                return
            # If it's a new album, mark it as being processed.
            processed_albums.add(album_id)
            logging.info("Processing new album with ID: %s", album_id)

        try:
            if ev.is_channel and ev.chat.id in tracked_ids:
                # Decide whether to reply based on REPLY_CHANCE
                if random.random() > REPLY_CHANCE:
                    logging.info("🎲 Skipped reply due to REPLY_CHANCE (%.2f)", REPLY_CHANCE)
                    return

                logging.info("✅ Matched post in channel: %s. Text: \"%s...\"", ev.chat.title, (ev.text or "")[:50])
                answer = ""
                try:
                    # Extract image if present
                    image_data, image_mime = await extract_image_from_message(ev.message)

                    # If no image and no text, skip. This is important for albums where text might be on a different part.
                    # The current logic handles the first event, which is usually sufficient.
                    if not image_data and not ev.text:
                        logging.info("No text or image found in this part of the post, skipping reply.")
                        return

                    # Generate reply with smart_reply
                    answer = await asyncio.wait_for(smart_reply(ev.text or "", PROMPT_TPL, image_data, image_mime), timeout=30)
                except asyncio.TimeoutError:
                    logging.warning("Gemini response timed out after 30s. Sending fallback.")
                    answer = FALLBACK

                if answer: # Only reply if smart_reply returned a non-empty string
                    # Human-like delay before sending the reply to avoid flood waits
                    delay = random.uniform(5, 10)
                    logging.info("Waiting for %.1f seconds before replying...", delay)
                    await asyncio.sleep(delay)

                    await clientTG.send_message(
                        ev.chat_id,
                        answer,
                        comment_to=ev.id
                    )
                    logging.info("💬 Replied in %s to message %s", ev.chat.title, ev.id)
                else:
                    logging.info("📝 Post did not generate a reply, skipped.")
        finally:
            # Clean up the album ID from the set after a short delay.
            # This ensures all parts of an album have arrived and been ignored.
            if album_id:
                await asyncio.sleep(5) # 5 seconds should be enough
                if album_id in processed_albums:
                    processed_albums.remove(album_id)
                    logging.info("Cleaned up album ID: %s", album_id)

    logging.info("Userbot ONLINE (Gemini‑Flash)…")
    await clientTG.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
