# tg-userbot


**Однажды меня спросили: "_Даня, почему ты не читаешь каналы_". Я устал оправдываться, что у меня мало времени, и решил создать данного бота.** 


**tg-userbot** — это Telegram-юзербот, автоматически публикующий комментарии к новым постам в канале и отвечающий на ответы пользователей, используя модель **Gemini 2.0 Flash**.

---

## Возможности

- Автоматический комментарий к каждому новому посту каналов из подписки.
- Ответ на сообщения пользователей, если они отвечают на комментарий бота.
- Генерация текста через Google Gemini 2.0 Flash.
- Гибкая настройка промптов и модели через `.env`.

---

## Быстрый старт

```bash
git clone https://github.com/tdrkn/tg_userbot.git
cd tg_userbot
cp .env.example .env 
docker compose up -d --build
```

---

## .env (пример)

```env
TG_API_ID=...
TG_API_HASH=...
TG_SESSION=...
TG_TARGET=@your_channel
GEMINI_KEY=...
GEMINI_MODEL=gemini-2.0-flash
GEMINI_PROMPT_POST=Комментарий к посту: «{text}»
GEMINI_PROMPT_REPLY=Ответ на сообщение: «{text}»
TG_REPLY_TEXT= …
```

---

## Зависимости

- `telethon==1.*`
- `google-genai==0.2.*`

---

## Лицензия

MIT License © 2025 [Danil Rastyapin]
