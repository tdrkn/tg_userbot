
FROM python:3.12-slim

# 1) копируем и ставим зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) копируем скрипт
COPY auto_reply_userbot.py /app/
WORKDIR /app

# 3) по умолчанию запускаем бот
CMD ["python", "auto_reply_userbot.py"]

