import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Set
from telethon import TelegramClient, events
from telethon.sessions import StringSession

from . import config
from .logging_setup import setup_logging
from .ai import init_gemini, test_gemini, smart_reply, generate_vibe_summary
from .telegram_utils import (
    extract_image_from_message,
    ensure_join,
    load_targets_from_csv,
    human_delay,
)
from .context_manager import VibeManager, MessageBuffer

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

    # Initialize Context Managers
    vibe_manager = VibeManager(config.VIBE_FILE)
    await vibe_manager.load()

    msg_buffer = MessageBuffer()

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

    # --- Background Tasks ---

    # 1. Channel List Refresher
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

    # 2. Vibe Updater
    async def vibe_updater():
        while True:
            # Check a few channels every hour or so, spread out load?
            # Or just loop through all tracked channels every hour and check 'should_update'
            await asyncio.sleep(3600 * 4) # Check every 4 hours
            logger.info("Running periodic vibe update check...")
            current_ids = list(tracked_ids)
            for cid in current_ids:
                if vibe_manager.should_update(cid):
                    logger.info("Updating vibe for channel %s...", cid)
                    try:
                        # Fetch last 50-100 messages
                        history = await clientTG.get_messages(cid, limit=75)
                        text_corpus = ""
                        for h in history:
                            if h.text:
                                text_corpus += f"- {h.text}\n"

                        if len(text_corpus) > 100:
                            summary = await generate_vibe_summary(text_corpus[:30000]) # Limit chars
                            if summary:
                                await vibe_manager.update_vibe(cid, summary)
                                logger.info("Vibe updated for %s: %s", cid, summary[:50])
                            else:
                                logger.warning("Empty vibe summary generated for %s", cid)
                        else:
                            logger.info("Not enough text history for %s to generate vibe.", cid)

                    except Exception as e:
                        logger.error("Failed to update vibe for %s: %s", cid, e)

                    await asyncio.sleep(60) # Pause between updates

    asyncio.create_task(refresher())
    asyncio.create_task(vibe_updater())

    processed_albums: Set[int] = set()

    async def process_batch(chat_id: int):
        """Processes a gathered batch of messages for a specific channel."""
        batch = msg_buffer.get_and_clear(chat_id)
        if not batch:
            return

        logger.info("Processing batch of %d messages for chat %d", len(batch), chat_id)

        # Get channel vibe
        vibe = vibe_manager.get_vibe(chat_id)

        # Logic to decide which message to reply to.
        # User implies replying to the "last" message but considering the context of all.
        last_msg_item = batch[-1]
        last_msg_id = last_msg_item['id']

        answer = ""
        # Retry logic for Gemini
        for attempt in range(3):
            try:
                # smart_reply now takes the batch list
                answer = await asyncio.wait_for(
                    smart_reply(batch, vibe_context=vibe),
                    timeout=45 # Slightly longer timeout for batch processing
                )
                break
            except Exception as e:
                logger.warning("Gemini batch attempt %d failed: %s", attempt + 1, e)
                if attempt < 2:
                    await asyncio.sleep(2)
                else:
                    logger.error("Gemini Error: Did not receive an answer after 3 attempts. Error: %s", e)
                    answer = ""

        if answer:
            await human_delay(5, 10)
            try:
                await clientTG.send_message(chat_id, answer, comment_to=last_msg_id)
                logger.info("Replied in %s to batch (last msg %s)", chat_id, last_msg_id)
            except Exception as e:
                logger.error("Failed to send reply to %s: %s", chat_id, e)
        else:
            logger.info("Batch did not generate a reply.")


    @clientTG.on(events.NewMessage())
    async def on_post(ev):
        # Ignore messages that are older than the bot's start time to prevent replying to history.
        if ev.date < start_time:
            return

        # Handle albums (deduplication of events)
        # Note: With batching, album events will naturally fall into the same batch window.
        # But we still want to avoid processing the same grouped_id multiple times as separate triggers if possible,
        # OR we just let them pile into the batch.
        # Actually, adding them all to the batch is better because they might have different images/text.
        # But Telethon sends separate events for each item in an album.

        # If we buffer, we don't strictly need 'processed_albums' for deduplication anymore,
        # essentially the buffer ACTS as the album grouper + debounce.

        if ev.is_channel and ev.chat.id in tracked_ids:
            logger.info("Received post in channel %s: %s", ev.chat_id, ev.id)

            # Extract data
            try:
                image_data, image_mime = await extract_image_from_message(ev.message)
            except Exception as e:
                logger.warning("Image extraction failed: %s", e)
                image_data, image_mime = None, None

            msg_data = {
                'id': ev.id,
                'text': ev.text or "",
                'image_data': image_data,
                'image_mime': image_mime
            }

            # Add to buffer
            msg_buffer.add_message(ev.chat_id, msg_data)

            # Schedule execution
            # Create a task that waits BATCH_DELAY then runs process_batch
            # If a task already exists for this channel, cancel it (debounce)
            async def delayed_trigger():
                try:
                    await asyncio.sleep(config.BATCH_DELAY)
                    await process_batch(ev.chat_id)
                except asyncio.CancelledError:
                    pass # Timer reset

            task = asyncio.create_task(delayed_trigger())
            msg_buffer.set_timer(ev.chat_id, task)

    logger.info("Userbot ONLINE…")
    await clientTG.run_until_disconnected()
