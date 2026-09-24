"""Точка входа: Flask-сервер, принимающий webhook от Telegram."""

import os                                          # для чтения переменных окружения
from flask import Flask, request                   # Flask-сервер и объект запроса
import telebot                                     # для разбора обновлений от Telegram

import database                                    # работа с БД
import handlers                                    # ← импорт регистрирует @bot.message_handler
from core import bot                               # объект бота


app = Flask(__name__)                              # создаём Flask-приложение
database.init_db()                                 # инициализируем таблицы

SECRET = os.environ.get("WEBHOOK_SECRET", "change_me_secret")  # секретный токен в URL (защита от фейковых запросов)
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")                # публичный URL нашего сервиса на Render


@app.route("/", methods=["GET"])                   # health-check: Render периодически стучит сюда
def healthcheck():                                 # функция-обработчик
    return "AI Freelancer Bot is alive", 200       # отвечаем 200 OK — значит, сервис жив


@app.route(f"/webhook/{SECRET}", methods=["POST"]) # Telegram будет POSTить сюда
def receive_webhook():                             # функция-обработчик webhook
    if request.headers.get("content-type") == "application/json":  # проверяем тип запроса
        json_data = request.get_data().decode("utf-8")             # берём тело запроса как строку
        update = telebot.types.Update.de_json(json_data)           # превращаем JSON в объект Update
        bot.process_new_updates([update])                          # передаём объект нашему боту
        return "", 200                                             # отвечаем "принято"
    return "Invalid content type", 403                             # если что-то другое — отказ


if WEBHOOK_URL:                                    # если URL задан (мы на Render) — регистрируем webhook
    try:                                           # пробуем
        bot.remove_webhook()                       # удаляем старый webhook (если был)
        bot.set_webhook(url=f"{WEBHOOK_URL}/webhook/{SECRET}")     # ставим новый
        print(f"✅ Webhook зарегистрирован: {WEBHOOK_URL}")
    except Exception as e:                         # если не получилось
        print(f"⚠ Webhook не зарегистрирован: {e}")


if __name__ == "__main__":                         # этот блок выполняется ТОЛЬКО при локальном запуске
    port = int(os.environ.get("PORT", 5000))       # Render даёт порт через переменную PORT
    app.run(host="0.0.0.0", port=port)             # запускаем Flask-сервер
