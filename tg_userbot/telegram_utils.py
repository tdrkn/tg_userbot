import asyncio
import csv
import logging
import random
from typing import Optional
import aiofiles
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors.rpcerrorlist import FloodWaitError, UserAlreadyParticipantError

logger = logging.getLogger(__name__)

async def extract_image_from_message(message) -> tuple[Optional[bytes], Optional[str]]:
    try:
        if not getattr(message, 'photo', None):
            return None, None
        image_bytes = await message.download_media(file=bytes)
        if not image_bytes:
            return None, None
        mime_type = "image/jpeg"
        if len(image_bytes) > 15 * 1024 * 1024:
            logger.warning("Image too large (%d bytes), skipping", len(image_bytes))
            return None, None
        logger.info("Downloaded image: %d bytes", len(image_bytes))
        return image_bytes, mime_type
    except Exception as e:
        logger.warning("Failed to extract image from message: %s", e)
        return None, None

async def ensure_join(clientTG, t: str):
    target = t.strip().rstrip(':\u200b\u200c\u200d')
    entity = None
    if "joinchat" in target or target.startswith("https://t.me/"):
        hash = target.rsplit("/", 1)[-1].lstrip("+")
        try:
            await clientTG(ImportChatInviteRequest(hash))
            entity = await clientTG.get_entity(target)
        except Exception as e:
            logger.warning("Invite join failed for %s: %s", target, e)
    if not entity:
        try:
            entity = await clientTG.get_entity(target)
        except Exception as e:
            logger.warning("Cannot resolve entity for %s: %s", target, e)
            return None
    try:
        await clientTG(JoinChannelRequest(entity))
    except UserAlreadyParticipantError:
        pass
    except FloodWaitError as e:
        logger.warning("Flood wait for %s seconds when joining %s", e.seconds, target)
        await asyncio.sleep(e.seconds + 5)
    except Exception as e:
        logger.error("Failed to join %s: %s", target, e)
        return None
    return entity

async def load_targets_from_csv(path: str) -> list[str]:
    try:
        async with aiofiles.open(path, mode="r", encoding="utf-8") as f:
            text = await f.read()
        return [row[0].strip() for row in csv.reader(text.splitlines()) if row and row[0].strip()]
    except FileNotFoundError:
        logger.warning("'%s' not found. No channels will be tracked.", path)
        return []
    except Exception as e:
        logger.error("Failed to read or parse '%s': %s", path, e)
        return []

async def human_delay(min_s: float = 5.0, max_s: float = 15.0):
    delay = random.uniform(min_s, max_s)
    logger.info("Waiting for %.1f seconds before next action...", delay)
    await asyncio.sleep(delay)

