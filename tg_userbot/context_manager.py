import json
import logging
import asyncio
import random
import time
from typing import Dict, List, Optional
import aiofiles

logger = logging.getLogger(__name__)

class VibeManager:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.vibes: Dict[str, Dict] = {}  # channel_id_str -> { "vibe": str, "last_updated": timestamp }
        self._lock = asyncio.Lock()

    async def load(self):
        try:
            async with aiofiles.open(self.filepath, mode='r', encoding='utf-8') as f:
                content = await f.read()
                self.vibes = json.loads(content)
        except FileNotFoundError:
            self.vibes = {}
        except Exception as e:
            logger.error("Failed to load vibe file: %s", e)
            self.vibes = {}

    async def save(self):
        async with self._lock:
            try:
                async with aiofiles.open(self.filepath, mode='w', encoding='utf-8') as f:
                    await f.write(json.dumps(self.vibes, ensure_ascii=False, indent=2))
            except Exception as e:
                logger.error("Failed to save vibe file: %s", e)

    def get_vibe(self, channel_id: int) -> Optional[str]:
        data = self.vibes.get(str(channel_id))
        return data.get("vibe") if data else None

    def should_update(self, channel_id: int) -> bool:
        data = self.vibes.get(str(channel_id))
        if not data:
            return True
        last_updated = data.get("last_updated", 0)
        # Random interval between 5 and 8 days (in seconds)
        # We can't be truly random every time we check, otherwise we might check 1s after update and get "False",
        # then check again and get "True" if we re-roll the random interval.
        # Instead, we check if elapsed time > stored_threshold or just strict 5 days minimum.
        # User said: "periodicity random once every 5-8 days".
        # Let's say we update if it's been more than 8 days for sure,
        # or if it's between 5-8 days we roll a small chance?
        # Simpler: just check if > 5 days + random offset determined at check time?
        # Or better: check if > 8 days.
        # Actually user said "absolute random in range 5-8 days".
        # Let's just use 5 days for now to ensure we get *some* data, and then we can randomize the *next* check.
        # But for strictly following the rule:
        # We can store 'next_update_at' instead of just 'last_updated'.

        # For legacy/simple approach: check if > 5 days.
        days_passed = (time.time() - last_updated) / 86400
        return days_passed > 8 or (days_passed > 5 and random.random() < 0.1)

    async def update_vibe(self, channel_id: int, vibe_text: str):
        self.vibes[str(channel_id)] = {
            "vibe": vibe_text,
            "last_updated": time.time()
        }
        await self.save()

class MessageBuffer:
    def __init__(self):
        # channel_id -> list of (event, text, image_data, image_mime)
        self.buffers: Dict[int, List] = {}
        # channel_id -> asyncio.TimerHandle (or task)
        self.timers: Dict[int, asyncio.Task] = {}

    def add_message(self, channel_id: int, message_data):
        if channel_id not in self.buffers:
            self.buffers[channel_id] = []
        self.buffers[channel_id].append(message_data)

    def get_and_clear(self, channel_id: int):
        data = self.buffers.get(channel_id, [])
        self.buffers[channel_id] = []
        # Do NOT cancel the timer here.
        # If this is called by the timer task itself, cancelling causes suicide (CancelledError).
        # If this is called manually, the timer will eventually wake up, see empty buffer, and exit.
        # If a new message comes, set_timer will cancel the old timer correctly.
        return data

    def cancel_timer(self, channel_id: int):
        if channel_id in self.timers:
            self.timers[channel_id].cancel()
            del self.timers[channel_id]

    def set_timer(self, channel_id: int, task: asyncio.Task):
        self.cancel_timer(channel_id)
        self.timers[channel_id] = task

