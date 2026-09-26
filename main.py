"""Точка входа: Flask-сервер, принимающий webhook от Telegram."""

import os
import sys
import traceback
import threading
import logging

from flask import Flask, request
import telebot

import database
import handlers                                # регистрирует все @bot.message_handler
from core import bot                           # объект бота

bot.threaded = False

# Включаем логирование telebot — теперь его ошибки попадут в лог Render
logging.basicConfig(level=logging.INFO, stream=sys.stdout)


app = Flask(__name__)
database.init_db()
database.init_jobs_table()
database.init_filters_table()
database.init_sent_table()

SECRET = os.environ.get("WEBHOOK_SECRET", "change_me_secret")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")


@app.route("/", methods=["GET"])
def healthcheck():
    return "AI Freelancer Bot is alive", 200


@app.route(f"/webhook/{SECRET}", methods=["POST"])
def receive_webhook():
    try:
        if request.headers.get("content-type", "").startswith("application/json"):
            json_data = request.get_data().decode("utf-8")
            print(f"📩 Апдейт получен ({len(json_data)} байт)", flush=True)

            update = telebot.types.Update.de_json(json_data)
            print(f"🔍 update_id={update.update_id}", flush=True)
            if update.message:
                print(f"💬 Текст: {update.message.text}", flush=True)

            bot.process_new_updates([update])
            print(f"✅ Апдейт обработан", flush=True)
            return "", 200
        return "Invalid content type", 403
    except Exception as e:
        print(f"🔥 ОШИБКА в webhook:\n{traceback.format_exc()}", flush=True)
        return "", 500


@app.route("/cron", methods=["GET", "POST"])
def cron_task():
    """Мгновенный ответ + работа в фоне (cron-job.org не ждёт)."""
    def background_job():
        try:
            import jobs as jobs_module
            print("\u23F0 Cron: фоновая задача запущена", flush=True)
            stats = jobs_module.broadcast_to_all_users()
            print(f"\u2705 Cron завершён: {stats}", flush=True)
        except Exception as e:
            import traceback
import threading
            print(f"\U0001F525 Cron упал:\n{traceback.format_exc()}", flush=True)

    thread = threading.Thread(target=background_job, daemon=True)
    thread.start()
    return {"status": "started", "message": "Работа идёт в фоне"}, 200



if WEBHOOK_URL:

    try:
        bot.remove_webhook()
        bot.set_webhook(url=f"{WEBHOOK_URL}/webhook/{SECRET}")
        print(f"✅ Webhook зарегистрирован: {WEBHOOK_URL}", flush=True)
    except Exception as e:
        print(f"⚠ Webhook не зарегистрирован: {e}", flush=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
