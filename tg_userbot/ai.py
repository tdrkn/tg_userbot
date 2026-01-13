import logging
from typing import Optional, List, Dict, Any

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


async def generate_vibe_summary(messages_text: str) -> str:
    """Generate a summary describing the channel's 'vibe' from recent messages."""
    if not _model:
        return ""

    prompt = (
        "Проанализируй последние сообщения из телеграм-канала ниже. "
        "Опиши кратко «вайб» канала, стиль общения, основные темы и тональность. "
        "Это нужно, чтобы я мог потом отвечать в том же духе. "
        "Твой ответ должен быть кратким описанием стиля (1-2 предложения).\n\n"
        f"Сообщения:\n{messages_text}"
    )

    try:
        response = await _model.generate_content_async(
            prompt,
            safety_settings=SAFETY_SETTINGS
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
    if not _model:
        logger.warning("smart_reply called but Gemini model is not available.")
        return ""

    if not message_batch:
        return ""

    # Construct the prompt
    # If we have a vibe, prepend it.
    system_instruction = ""
    if vibe_context:
        system_instruction += f"Контекст канала (стиль/вайб): {vibe_context}\n\n"

    combined_text = ""
    all_images = []

    for msg in message_batch:
        txt = msg.get('text', '')
        if txt:
            combined_text += f"- {txt}\n"

        img_data = msg.get('image_data')
        img_mime = msg.get('image_mime')
        if img_data and img_mime:
            all_images.append({"mime_type": img_mime, "data": img_data})

    if not combined_text and not all_images:
        return ""

    # Use the template from config, treating combined_text as the input
    main_prompt = config.PROMPT_TPL.format(text=combined_text.strip())

    # If purely images without text, switch template if needed
    if not combined_text.strip() and all_images:
        main_prompt = config.PROMPT_IMAGE_ONLY

    final_prompt = f"{system_instruction}{main_prompt}"

    # Construct content list for Gemini
    content = [final_prompt]

    # Attach images (limit to first or last few to avoid token limits? Gemini handles many images usually)
    # Let's attach all images from the batch.
    content.extend(all_images)

    try:
        response = await _model.generate_content_async(
            content,
            safety_settings=SAFETY_SETTINGS
        )

        if not getattr(response, 'parts', None):
            logger.warning("Gemini response was empty or blocked by safety filters.")
            return ""

        return (response.text or "").strip()
    except Exception as e:
        logger.error("Gemini generation error: %s", e)
        raise e  # Propagate to allow retry logic in main.py
