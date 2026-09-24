"""Настройки проекта."""

import os

DB_PATH = os.environ.get("DB_PATH", "bot.db")

AI_MODEL = "gemini-3.5-flash-lite"
MAX_ATTEMPTS = 3

TELEGRAM_MAX_LEN = 4000                                        # максимальная длина одного сообщения в Telegram (4096 — это лимит, берём с запасом)
