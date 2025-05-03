FROM python:3.12-slim
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY auto_reply_userbot.py /app/
WORKDIR /app
CMD ["python", "auto_reply_userbot.py"]
