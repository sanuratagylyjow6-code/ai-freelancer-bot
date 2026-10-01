"""Демо-бот на aiogram 3.x — только для обучения.

НЕ запускается на Render — используем как эталон.
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode


BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # ← для реального запуска

logging.basicConfig(level=logging.INFO)


# --- Создаём бота и диспетчера ---
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()


# --- Handlers (все async!) ---

@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик /start."""
    user_name = message.from_user.first_name or "друг"
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Привет"), KeyboardButton(text="Помощь")]],
        resize_keyboard=True
    )
    await message.answer(
        f"Привет, <b>{user_name}</b>!",
        reply_markup=kb
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "Я демо-бот на <b>aiogram</b>.\n"
        "Команды: /start, /help"
    )


@dp.message(F.text == "Привет")
async def on_hello(message: Message):
    """Реакция на кнопку «Привет»."""
    await message.answer("И тебе привет! 👋")


@dp.message(F.text == "Помощь")
async def on_help_btn(message: Message):
    await message.answer("Это демо. Все команды: /start, /help")


@dp.message(F.text)
async def echo_all(message: Message):
    """Эхо на любое сообщение."""
    await message.answer(f"Ты написал: <code>{message.text}</code>")


# --- Точка входа ---
async def main():
    print("Бот запущен (polling)...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
