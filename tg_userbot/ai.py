import logging
from typing import Optional, List, Dict, Any

from google import genai
from google.genai import types

from . import config

logger = logging.getLogger(__name__)

_client: Optional[genai.Client] = None

def is_ready() -> bool:
    return _client is not None


def init_gemini() -> Optional[genai.Client]:
    """Initialize Google Gemini client using environment configuration."""
    global _client
    if not config.GEMINI_KEY:
        logger.warning("GEMINI_KEY not found. AI features will be disabled.")
        return None
    try:
        _client = genai.Client(api_key=config.GEMINI_KEY)
        logger.info("Gemini client initialized for model '%s'.", config.GEMINI_MODEL_NAME)
        return _client
    except Exception as e:
        logger.error("Failed to initialize Gemini client: %s", e, exc_info=True)
        _client = None
        return None

def _get_safety_config() -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        safety_settings=[
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
        ]
    )

async def test_gemini():
    """Perform a simple test call to verify Gemini connectivity."""
    if not _client:
        logger.warning("Skipping Gemini test because client is not initialized.")
        return
    try:
        logger.info("Performing a test query to Gemini...")
        test_prompt = "Hello! This is a test prompt. If you see this, please respond with just the word 'OK'."
        response = await _client.aio.models.generate_content(
            model=config.GEMINI_MODEL_NAME,
            contents=test_prompt,
        )
        if response.text and 'OK' in response.text:
            logger.info("Gemini test successful.")
        else:
            logger.warning("Gemini test returned unexpected response.")
    except Exception as e:
        logger.error("Gemini test failed with an error: %s", e, exc_info=True)


async def generate_vibe_summary(messages_text: str) -> str:
    """Generate a summary describing the channel's 'vibe' from recent messages."""
    if not _client:
        return ""

    prompt = (
        "Проанализируй последние сообщения из телеграм-канала ниже. "
        "Опиши кратко «вайб» канала, стиль общения, основные темы и тональность. "
        "Это нужно, чтобы я мог потом отвечать в том же духе. "
        "Твой ответ должен быть кратким описанием стиля (1-2 предложения).\n\n"
        f"Сообщения:\n{messages_text}"
    )

    try:
        response = await _client.aio.models.generate_content(
            model=config.GEMINI_MODEL_NAME,
            contents=prompt,
            config=_get_safety_config()
        )
        return (response.text or "").strip()
    except Exception as e:
        logger.error("Failed to generate vibe summary: %s", e)
        return ""


async def smart_reply(message_batch: List[Dict[str, Any]],
                      vibe_context: str | None = None) -> str:
    """
    Generate a reply using Gemini based on a batch of messages

    :param message_batch: List of dicts with 'text' (str), 'image_data' (bytes, opt), 'image_mime' (str, opt)
    :param vibe_context: Optional string describing the channel's style/context
    """
    if not _client:
        logger.warning("smart_reply called but Gemini client is not available.")
        return ""

    if not message_batch:
        return ""

    # Construct the prompt
    system_instruction = ""
    if vibe_context:
        system_instruction += f"Контекст канала (стиль/вайб): {vibe_context}\n\n"

    combined_text = ""
    image_parts = []

    for msg in message_batch:
        txt = msg.get('text', '')
        if txt:
            combined_text += f"- {txt}\n"

        img_data = msg.get('image_data')
        img_mime = msg.get('image_mime')
        if img_data and img_mime:
            try:
                part = types.Part.from_bytes(data=img_data, mime_type=img_mime)
                image_parts.append(part)
            except Exception as e:
                logger.warning("Failed to create image part: %s", e)

    if not combined_text and not image_parts:
        return ""

    # Use the template from config
    main_prompt = config.PROMPT_TPL.format(text=combined_text.strip())

    # If purely images without text, switch template if needed
    if not combined_text.strip() and image_parts:
        main_prompt = config.PROMPT_IMAGE_ONLY

    final_prompt = f"{system_instruction}{main_prompt}"

    # Construct content list for Gemini
    contents = [final_prompt]
    contents.extend(image_parts)

    try:
        response = await _client.aio.models.generate_content(
            model=config.GEMINI_MODEL_NAME,
            contents=contents,
            config=_get_safety_config()
        )

        if not response.text:
             logger.warning("Gemini response was empty or blocked.")
             return ""

        return (response.text or "").strip()
    except Exception as e:
        logger.error("Gemini generation error: %s", e)
        raise e  # Propagate to allow retry logic in main.py
