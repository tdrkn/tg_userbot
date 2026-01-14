import logging
from . import config

def setup_logging():
    level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(config.LOG_FILE),
            logging.StreamHandler()
        ],
        force=True
    )

    # Suppress noisy logs from third-party libraries
    # Aggressively silence Telethon
    logging.getLogger("telethon").setLevel(logging.ERROR)
    logging.getLogger("telethon.network").setLevel(logging.CRITICAL)  # Network mostly spam
    logging.getLogger("telethon.extensions").setLevel(logging.CRITICAL)

    # Walk through all existing loggers to ensure sub-loggers are silenced
    for logger_name in logging.root.manager.loggerDict:
        if logger_name.startswith("telethon"):
             logging.getLogger(logger_name).setLevel(logging.ERROR)

    # Others to WARNING or ERROR
    logging.getLogger("google").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.ERROR)  # Asyncio warnings can be redundant

    return logging.getLogger(__name__)

