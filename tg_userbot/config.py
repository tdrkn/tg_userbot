import os
from dotenv import load_dotenv

# Load .env from current working directory (useful in Docker or local runs)
load_dotenv()

# Environment variables
GEMINI_KEY = os.getenv("GEMINI_KEY")
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
PROMPT_TPL = os.getenv("GEMINI_PROMPT", "Напиши комментарий к этому посту: «{text}»")
# Support both names for image-only prompt
PROMPT_IMAGE_ONLY = os.getenv("GEMINI_PROMPT_IMAGE") or os.getenv("PROMPT_IMAGE_TPL") or "Напиши короткий комментарий к этому изображению, не описывая его."
# Optional reply prompt (not used yet by runner, reserved for future use)
PROMPT_REPLY_TPL = os.getenv("GEMINI_PROMPT_REPLY")
FALLBACK = os.getenv("TG_REPLY_TEXT", "🤖 ...")

TG_API_ID = os.getenv("TG_API_ID")
TG_API_HASH = os.getenv("TG_API_HASH")
TG_SESSION = os.getenv("TG_SESSION")

CHANNELS_CSV = os.getenv("CHANNELS_CSV", "channels.csv")

LOG_FILE = os.getenv("LOG_FILE", "bot.log")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
