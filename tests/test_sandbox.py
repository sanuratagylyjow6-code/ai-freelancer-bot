"""Тесты sandbox: подмена токенов, удаление блокирующих вызовов."""
import sys
sys.path.insert(0, "/content/project")

from sandbox import _prepare_project


def test_replace_polling():
    files = {
        "bot.py": "import telebot\nbot = telebot.TeleBot('1234567890:AAA')\nbot.infinity_polling()"
    }
    result = _prepare_project(files, "bot.py")
    assert "bot.infinity_polling" not in result["bot.py"]
    assert "would start polling" in result["bot.py"]


def test_replace_placeholder_token():
    files = {
        "config.py": "BOT_TOKEN = 'YOUR_BOT_TOKEN_HERE'",
        "bot.py": "from config import BOT_TOKEN\nprint(BOT_TOKEN)"
    }
    result = _prepare_project(files, "bot.py")
    assert "YOUR_BOT_TOKEN_HERE" not in result["config.py"]
    assert "1234567890:" in result["config.py"]


def test_replace_app_run():
    files = {
        "main.py": "from flask import Flask\napp = Flask(__name__)\napp.run(host='0.0.0.0')"
    }
    result = _prepare_project(files, "main.py")
    assert "# app.run(" in result["main.py"]
