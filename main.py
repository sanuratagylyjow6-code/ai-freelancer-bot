"""Точка входа: Flask-сервер для webhook + cron."""

import os
import sys
import traceback
import logging
import threading

from flask import Flask, request
import telebot

import database
import handlers
from core import bot

# Отключаем многопоточность telebot — обработчики выполняются синхронно
bot.threaded = False

# Логирование telebot в stdout (чтобы ошибки были видны в Render Logs)
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
    """Healthcheck для UptimeRobot и Render."""
    return "AI Freelancer Bot is alive", 200


@app.route(f"/webhook/{SECRET}", methods=["POST"])
def receive_webhook():
    """Принимает апдейты от Telegram."""
    try:
        if request.headers.get("content-type", "").startswith("application/json"):
            json_data = request.get_data().decode("utf-8")
            print(f"\U0001F4E9 Апдейт получен ({len(json_data)} байт)", flush=True)
            update = telebot.types.Update.de_json(json_data)
            print(f"\U0001F50D update_id={update.update_id}", flush=True)
            if update.message:
                print(f"\U0001F4AC Текст: {update.message.text}", flush=True)
            bot.process_new_updates([update])
            print(f"\u2705 Апдейт обработан", flush=True)
            return "", 200
        return "Invalid content type", 403
    except Exception as e:
        print(f"\U0001F525 ОШИБКА в webhook:\n{traceback.format_exc()}", flush=True)
        return "", 500


_cron_lock = threading.Lock()


@app.route("/cron", methods=["GET", "POST"])
def cron_task():
    """Запускает рассылку в фоне, но только если другой процесс не идёт."""
    def background_job():
        acquired = _cron_lock.acquire(blocking=False)
        if not acquired:
            print("⏭ Cron уже выполняется, пропускаю", flush=True)
            return
        try:
            import jobs as jobs_module
            print("\u23F0 Cron: фоновая задача запущена", flush=True)
            stats = jobs_module.broadcast_to_all_users()
            print(f"\u2705 Cron завершён: {stats}", flush=True)
        except Exception:
            print(f"\U0001F525 Cron упал:\n{traceback.format_exc()}", flush=True)
        finally:
            _cron_lock.release()

    thread = threading.Thread(target=background_job, daemon=True)
    thread.start()
    return {"status": "started", "message": "Работа идёт в фоне"}, 200



if WEBHOOK_URL:
    try:
        bot.remove_webhook()
        bot.set_webhook(url=f"{WEBHOOK_URL}/webhook/{SECRET}")
        print(f"\u2705 Webhook зарегистрирован: {WEBHOOK_URL}", flush=True)
    except Exception as e:
        print(f"\u26A0 Webhook не зарегистрирован: {e}", flush=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
