"""Настройки проекта."""

import os

DB_HOST = os.environ.get("DB_HOST")
DB_PORT = os.environ.get("DB_PORT", "6543")
DB_NAME = os.environ.get("DB_NAME", "postgres")
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")

AI_MODEL = "gemini-3.5-flash-lite"
MAX_ATTEMPTS = 3
TELEGRAM_MAX_LEN = 4000
