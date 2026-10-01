"""Точка входа: Flask-сервер, принимающий webhook от Telegram."""

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

bot.threaded = False
logging.basicConfig(level=logging.INFO, stream=sys.stdout)


app = Flask(__name__)
database.init_db()
database.init_projects_table()
database.init_full_projects_table()


SECRET = os.environ.get("WEBHOOK_SECRET", "change_me_secret")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")


@app.route("/", methods=["GET"])
def healthcheck():
    """Healthcheck для UptimeRobot и Render."""
    return "AI Python Developer Bot is alive", 200


@app.route(f"/webhook/{SECRET}", methods=["POST"])
def receive_webhook():
    """Принимает апдейты от Telegram."""
    try:
        if request.headers.get("content-type", "").startswith("application/json"):
            json_data = request.get_data().decode("utf-8")
            update = telebot.types.Update.de_json(json_data)
            bot.process_new_updates([update])
            return "", 200
        return "Invalid content type", 403
    except Exception as e:
        print(f"\U0001F525 ОШИБКА в webhook:\n{traceback.format_exc()}", flush=True)
        return "", 500


@app.route("/dashboard", methods=["GET"])
def dashboard_page():
    """HTML-страница со статистикой проектов."""
    try:
        from dashboard import render_dashboard
        stats = database.get_dashboard_stats()
        stats["_chart_data"] = database.get_chart_data()
        return render_dashboard(stats), 200
    except Exception as e:
        return f"<h1>Ошибка дашборда</h1><pre>{traceback.format_exc()}</pre>", 500


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
