cat > auto_reply_userbot.py << 'EOF'
from telethon import TelegramClient, events
import os, logging

# 1) читаем настройки из переменных окружения
API_ID   = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")
TARGET   = os.getenv("TG_TARGET")       # канал вида @mychannel или ссылка
REPLY    = os.getenv("TG_REPLY_TEXT")   # текст ответа
SESSION  = "userbot_session"            # имя файла сессии

# 2) включаем простой лог
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

# 3) создаём клиент Telethon
client = TelegramClient(SESSION, API_ID, API_HASH)

# 4) хендлер на новые сообщения в TARGET
@client.on(events.NewMessage(chats=TARGET))
async def on_post(event):
    if event.is_channel and not event.is_group:
        await event.reply(REPLY, comment_to=event.id)
        logging.info("Replied to post %s", event.id)

# 5) запускаем бесконечный loop
with client:
    logging.info("Bot started, waiting for posts…")
    client.run_until_disconnected()
EOF
