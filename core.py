"""Создание объекта bot."""

import os
import telebot

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в переменных окружения")

bot = telebot.TeleBot(BOT_TOKEN)
