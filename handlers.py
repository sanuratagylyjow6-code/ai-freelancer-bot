"""Все обработчики команд Telegram-бота."""

import html
from core import bot
from database import (
    save_user, get_user_stats, get_all_clients,
    save_task, update_task, get_user_tasks
)
from ai import ask_ai, run_code, auto_fix
from parser import parse_quotes
from config import TELEGRAM_MAX_LEN, MAX_ATTEMPTS


def split_long_message(text, max_len=None):
    """Режет длинный текст на куски по max_len символов, стараясь резать по \\n."""
    max_len = max_len or TELEGRAM_MAX_LEN
    parts = []
    while len(text) > max_len:
        cut = text.rfind("\n", 0, max_len)
        if cut == -1:
            cut = max_len
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    parts.append(text)
    return parts


def send_code(message, code_text):
    """Отправляет код с HTML-экранированием и разбивкой по длине."""
    safe_text = html.escape(code_text)
    for part in split_long_message(safe_text):
        try:
            bot.reply_to(message, f"<pre>{part}</pre>", parse_mode="HTML")
        except Exception as e:
            bot.reply_to(message, f"⚠ Не смог отправить: {e}")

@bot.message_handler(commands=['start'])
def send_welcome(message):
    """Регистрирует пользователя и приветствует его."""
    try:
        print(f"📥 /start от user_id={message.from_user.id}", flush=True)
        user_id = message.from_user.id
        username = message.from_user.first_name or message.from_user.username or "без имени"
        print(f"👤 username={username}", flush=True)
        save_user(user_id, username)
        print(f"💾 save_user OK", flush=True)
        bot.reply_to(message, f"Привет, {username}! Я AI Freelancer Bot 🤖")
        print(f"✉️ Ответ отправлен", flush=True)
    except Exception as e:
        import traceback
        print(f"🔥 /start упал:\n{traceback.format_exc()}", flush=True)
        try:
            bot.reply_to(message, f"⚠ Ошибка: {e}")
        except Exception:
            pass


@bot.message_handler(commands=['help'])
def send_help(message):
    """Список всех команд бота."""
    bot.reply_to(
        message,
        "Команды:\n"
        "/start — приветствие\n"
        "/parse — спарсить цитаты\n"
        "/mystats — моя статистика\n"
        "/clients — все клиенты\n"
        "/code <задание> — сгенерировать код\n"
        "/run <задание> — сгенерировать и выполнить\n"
        "/history — последние задачи"
    )


@bot.message_handler(commands=['parse'])
def handle_parse(message):
    """Парсит тренировочный сайт и отправляет 5 цитат."""
    bot.reply_to(message, "Секунду, собираю данные... ⏳")
    try:
        items = parse_quotes()
        bot.reply_to(message, "\n".join(items[:5]))
    except Exception as e:
        bot.reply_to(message, f"⚠ Ошибка парсинга: {e}")


@bot.message_handler(commands=['mystats'])
def handle_stats(message):
    """Показывает статистику текущего пользователя."""
    user_id = message.from_user.id
    stats = get_user_stats(user_id)
    if stats is None:
        bot.reply_to(message, "Ты ещё не в базе. Напиши /start!")
        return
    username, first_seen, count = stats
    bot.reply_to(
        message,
        f"📊 Статистика:\n"
        f"👤 Имя: {username}\n"
        f"📅 Первый раз: {first_seen}\n"
        f"✉️ Сообщений: {count}"
    )


@bot.message_handler(commands=['clients'])
def handle_clients(message):
    """Список всех клиентов бота."""
    rows = get_all_clients()
    if not rows:
        bot.reply_to(message, "Клиентов пока нет.")
        return
    lines = [f"👥 Всего: {len(rows)}\n"]
    for i, row in enumerate(rows, start=1):
        _, username, first_seen, count = row
        lines.append(f"{i}. {username} — {count} сообщ.")
    bot.reply_to(message, "\n".join(lines))


@bot.message_handler(commands=['code'])
def handle_code(message):
    """Генерирует код по заданию через Gemini (без выполнения)."""
    prompt = message.text.replace("/code", "", 1).strip()
    if not prompt:
        bot.reply_to(message, "Напиши задание. Пример: /code функция факториала")
        return
    bot.reply_to(message, "🧠 Думаю...")
    system_prompt = (
        "Ты — опытный Python-разработчик. "
        "Пиши ТОЛЬКО код без markdown-обёрток. "
        "Короткие комментарии в коде — можно."
    )
    answer = ask_ai(f"{system_prompt}\n\nЗадание: {prompt}")
    send_code(message, answer)


@bot.message_handler(commands=['run'])
def handle_run(message):
    """Генерирует код, выполняет его и исправляет ошибки через Gemini."""
    try:
        prompt = message.text.replace("/run", "", 1).strip()
        if not prompt:
            bot.reply_to(message, "Напиши задание. Пример: /run сумма 1..100")
            return

        user_id = message.from_user.id
        bot.reply_to(message, "🧠 Генерирую код...")

        system_prompt = (
            "Ты — опытный Python-разработчик. "
            "Пиши ТОЛЬКО код без markdown. "
            "Используй print() для вывода результата. "
            "Не используй input()."
        )
        code = ask_ai(f"{system_prompt}\n\nЗадание: {prompt}")

        bot.reply_to(message, "💾 Сохраняю в БД...")
        task_id = save_task(user_id, prompt, code)

        bot.reply_to(message, f"⚙️ Задача #{task_id}. Запускаю...")

        attempts = 0
        success = False
        final_output = ""
        last_error = None

        while attempts < MAX_ATTEMPTS and not success:
            attempts += 1
            ok, result, namespace = run_code(code)
            if ok:
                success = True
                final_output = f"✅ Успех за {attempts} поп.\n\nКод:\n{code}"
            else:
                last_error = result
                if attempts < MAX_ATTEMPTS:
                    bot.reply_to(message, f"⚠️ Ошибка на попытке {attempts}. Отправляю ИИ на исправление...")
                    code = auto_fix(code, result)
                else:
                    final_output = f"❌ Не удалось за {MAX_ATTEMPTS} попытки:\n{result[:500]}"

        update_task(task_id, "success" if success else "error",
                    None if success else last_error[:500], attempts)
        send_code(message, final_output)

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        bot.reply_to(message, f"🔥 Ошибка в /run:\n{tb[-800:]}")


@bot.message_handler(commands=['history'])
def handle_history(message):
    """Показывает последние 5 задач пользователя."""
    user_id = message.from_user.id
    rows = get_user_tasks(user_id, limit=5)
    if not rows:
        bot.reply_to(message, "История пуста.")
        return
    lines = ["📜 Последние задачи:\n"]
    for task_id, prompt, status, attempts, created_at in rows:
        emoji = "✅" if status == "success" else "❌"
        short_prompt = prompt[:40] + ("..." if len(prompt) > 40 else "")
        lines.append(f"{emoji} #{task_id} ({attempts} поп.) {short_prompt}")
    bot.reply_to(message, "\n".join(lines))


@bot.message_handler(func=lambda m: not m.text.startswith('/'))
def echo_all(message):
    """Отвечает на любое не-командное сообщение."""
    bot.reply_to(message, f"Ты написал: {message.text}")
