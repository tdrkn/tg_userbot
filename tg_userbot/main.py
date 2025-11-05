import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Set
from telethon import TelegramClient, events
from telethon.sessions import StringSession

from . import config
from .logging_setup import setup_logging
from .ai import init_gemini, test_gemini, smart_reply
from .telegram_utils import (
    extract_image_from_message,
    ensure_join,
    load_targets_from_csv,
    human_delay,
)

logger = logging.getLogger(__name__)

async def run():
    setup_logging()
    logger.info("Starting userbot...")

    # Initialize Gemini
    init_gemini()

    # Get the current time in UTC when the bot starts.
    start_time = datetime.now(timezone.utc)
    logger.info("Bot started at %s. Ignoring messages older than this.", start_time)

    # Create Telegram client
    api_id = int(config.TG_API_ID) if config.TG_API_ID else None
    api_hash = config.TG_API_HASH
    session = config.TG_SESSION
    if not all([api_id, api_hash, session]):
        raise RuntimeError("Missing Telegram credentials in environment (TG_API_ID, TG_API_HASH, TG_SESSION)")

    clientTG = TelegramClient(StringSession(session), api_id, api_hash)
    await clientTG.start()

    # Test Gemini connection on startup
    await test_gemini()

    # Map of target string to entity ID
    target_to_id: Dict[str, int] = {}

    # Initial load from CSV
    logger.info("Starting initial channel setup...")
    csv_targets = await load_targets_from_csv(config.CHANNELS_CSV)
    for t in csv_targets:
        ent = await ensure_join(clientTG, t)
        if ent:
            # Some entities may not have title/username
            target_to_id[t] = ent.id
            logger.info("Tracking %s", getattr(ent, 'title', None) or getattr(ent, 'username', None) or ent.id)
        else:
            logger.warning("Skipped tracking %s", t)
        await human_delay(5, 15)

    logger.info("Initial channel setup complete.")
    tracked_ids: Set[int] = set(target_to_id.values())

    # Background task: refresh channels every 5 minutes
    async def refresher():
        nonlocal target_to_id, tracked_ids
        while True:
            await asyncio.sleep(300)
            logger.info("Refreshing channel list from CSV...")
            csv_targets = await load_targets_from_csv(config.CHANNELS_CSV)
            if not csv_targets:
                logger.warning("CSV is empty or could not be read. No changes to tracked channels.")
                continue
            current_targets = set(target_to_id.keys())
            new_targets = set(csv_targets) - current_targets
            for t in new_targets:
                ent = await ensure_join(clientTG, t)
                if ent:
                    target_to_id[t] = ent.id
                    logger.info("Started tracking new channel: %s", getattr(ent, 'title', None) or getattr(ent, 'username', None) or ent.id)
                else:
                    logger.warning("Skipped tracking new target: %s", t)
                await human_delay(5, 15)
            removed_targets = current_targets - set(csv_targets)
            for t in removed_targets:
                target_to_id.pop(t, None)
                logger.info("Stopped tracking channel: %s", t)
            tracked_ids = set(target_to_id.values())

    asyncio.create_task(refresher())

    processed_albums: Set[int] = set()

    @clientTG.on(events.NewMessage())
    async def on_post(ev):
        # Ignore messages that are older than the bot's start time to prevent replying to history.
        if ev.date < start_time:
            return

        # --- Album Handling ---
        album_id = ev.grouped_id
        if album_id:
            if album_id in processed_albums:
                logger.info("Ignoring duplicate message from album ID: %s", album_id)
                return
            processed_albums.add(album_id)
            logger.info("Processing new album with ID: %s", album_id)

        try:
            if ev.is_channel and ev.chat.id in tracked_ids:
                logger.info("Matched post in channel: %s. Text: \"%s...\"", getattr(ev.chat, 'title', None), (ev.text or '')[:50])
                answer = ""
                try:
                    image_data, image_mime = await extract_image_from_message(ev.message)
                    if not image_data and not ev.text:
                        logger.info("No text or image found in this part of the post, skipping reply.")
                        return
                    answer = await asyncio.wait_for(
                        smart_reply(ev.text or "", image_data, image_mime),
                        timeout=30
                    )
                except asyncio.TimeoutError:
                    logger.warning("Gemini response timed out after 30s. Sending fallback.")
                    from . import config as cfg
                    answer = cfg.FALLBACK

                if answer:
                    await human_delay(5, 10)
                    await clientTG.send_message(ev.chat_id, answer, comment_to=ev.id)
                    logger.info("Replied in %s to message %s", getattr(ev.chat, 'title', None), ev.id)
                else:
                    logger.info("Post did not generate a reply, skipped.")
        finally:
            if album_id:
                await asyncio.sleep(5)
                if album_id in processed_albums:
                    processed_albums.remove(album_id)
                    logger.info("Cleaned up album ID: %s", album_id)

    logger.info("Userbot ONLINE…")
    await clientTG.run_until_disconnected()
