import logging
from typing import Optional

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from . import config

logger = logging.getLogger(__name__)

# Safety settings for Gemini
SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

_model: Optional[genai.GenerativeModel] = None

def is_ready() -> bool:
    return _model is not None


def init_gemini() -> Optional[genai.GenerativeModel]:
    """Initialize Google Gemini client using environment configuration."""
    global _model
    if not config.GEMINI_KEY:
        logger.warning("GEMINI_KEY not found. AI features will be disabled.")
        return None
    try:
        genai.configure(api_key=config.GEMINI_KEY)
        _model = genai.GenerativeModel(config.GEMINI_MODEL_NAME)
        logger.info("Gemini model '%s' initialized.", config.GEMINI_MODEL_NAME)
        return _model
    except Exception as e:
        logger.error("Failed to initialize Gemini model: %s", e, exc_info=True)
        _model = None
        return None


async def test_gemini():
    """Perform a simple test call to verify Gemini connectivity."""
    if not _model:
        logger.warning("Skipping Gemini test because model is not initialized.")
        return
    try:
        logger.info("Performing a test query to Gemini...")
        test_prompt = "Hello! This is a test prompt. If you see this, please respond with just the word 'OK'."
        response = await _model.generate_content_async(test_prompt)
        if response and getattr(response, 'text', '').find('OK') != -1:
            logger.info("Gemini test successful.")
        else:
            logger.warning("Gemini test returned unexpected response.")
    except Exception as e:
        logger.error("Gemini test failed with an error: %s", e, exc_info=True)


async def smart_reply(post_text: str,
                      image_data: bytes | None = None,
                      image_mime: str | None = None) -> str:
    """Generate a reply using Gemini. Falls back to config.FALLBACK on issues."""
    if not _model:
        logger.warning("smart_reply called but Gemini model is not available.")
        return config.FALLBACK

    try:
        # Use image-only prompt if an image is present without text
        if image_data and not post_text:
            prompt = config.PROMPT_IMAGE_ONLY
        else:
            prompt = config.PROMPT_TPL.format(text=post_text)

        content = [prompt]
        if image_data and image_mime:
            content.append({"mime_type": image_mime, "data": image_data})

        response = await _model.generate_content_async(
            content,
            safety_settings=SAFETY_SETTINGS
        )

        if not getattr(response, 'parts', None):
            logger.warning("Gemini response was empty or blocked by safety filters.")
            return config.FALLBACK

        return (response.text or "").strip() or config.FALLBACK

    except Exception as e:
        logger.error("Error during Gemini API call for model '%s': %s", config.GEMINI_MODEL_NAME, e, exc_info=True)
        return config.FALLBACK
