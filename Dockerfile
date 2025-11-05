FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy package, env, and wrapper
COPY tg_userbot/ tg_userbot/
COPY auto_reply_userbot.py .
COPY channels.csv .
COPY .env .

CMD ["python", "auto_reply_userbot.py"]
