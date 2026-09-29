"""Все обработчики команд Telegram-бота."""

import html
from core import bot
from database import (
    save_user, get_user_stats, get_all_clients,
    save_task, update_task, get_user_tasks
)
from ai import (ask_ai, run_code, auto_fix, generate_project, edit_project, generate_full_project, generate_apply_draft, evaluate_budget)
from parser import parse_quotes
from jobs import fetch_from_telegram, fetch_all_sources
from database import (save_jobs, search_jobs, set_filter, get_filter, clear_filter,
                       save_project, get_user_projects, get_project, get_project_with_parent,
                       save_full_project, get_user_full_projects, get_full_project,
                       search_jobs_full, get_quick_stats, parse_filter_keywords,
                       save_note, get_user_notes, get_job_by_id,
                       set_job_status, get_job_status, get_jobs_by_status,
                       save_user_file, get_latest_user_file, clear_user_files)
from config import TELEGRAM_MAX_LEN, MAX_ATTEMPTS, OWNER_ID


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



# ============================================================
# ЗАЩИТА: бот доступен только владельцу
# ============================================================

def _is_owner(message):
    """Проверяет, что сообщение от владельца."""
    return message.from_user and message.from_user.id == OWNER_ID


@bot.message_handler(func=lambda m: not _is_owner(m))
def block_outsiders(message):
    """Блокирует всех, кроме владельца."""
    # Логируем попытку (в Render Logs)
    print("🚫 Попытка доступа от user_id=" + str(message.from_user.id) +
          " username=@" + str(message.from_user.username), flush=True)
    try:
        bot.reply_to(message, "⛔ Этот бот — приватный. Доступ только у владельца.")
    except Exception:
        pass


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


@bot.message_handler(commands=['find'])
def handle_find(message):
    """Ищет заказы во ВСЕХ источниках и сохраняет в БД."""
    keyword = message.text.replace("/find", "", 1).strip()
    bot.reply_to(message, "Сканирую все источники... 30-60 сек.")

    try:
        jobs = fetch_all_sources()
        if not jobs:
            bot.reply_to(message, "Ничего не нашлось.")
            return

        new_count = 0
        by_channel = {}
        for j in jobs:
            ch = j.get("channel", "unknown")
            by_channel.setdefault(ch, []).append(j)
        for ch, ch_jobs in by_channel.items():
            new_count += save_jobs(ch_jobs, ch)

        total = len(jobs)
        bot.reply_to(message, "Найдено " + str(total) + " вакансий (" + str(new_count) + " новых).")

        if keyword:
            results = search_jobs_full(keyword, limit=10)
            if not results:
                bot.reply_to(message, "По запросу '" + keyword + "' ничего нет.")
                return
            lines = ["Найдено " + str(len(results)) + " по '" + keyword + "':\n"]
            for jid, ch, cat, title, desc, url in results:
                lines.append("#" + str(jid) + " [" + cat + "] " + title)
                lines.append("   " + desc[:120] + "...")
                lines.append("   " + url + "\n")
            send_code(message, "\n".join(lines))
    except Exception as e:
        import traceback
        bot.reply_to(message, "Ошибка: " + traceback.format_exc()[-300:])


@bot.message_handler(commands=['search'])
def handle_search(message):
    """Поиск по всей БД. /search <слово>"""
    keyword = message.text.replace("/search", "", 1).strip()
    if len(keyword) < 2:
        bot.reply_to(message, "Формат: /search <слово>")
        return

    results = search_jobs_full(keyword, limit=15)
    if not results:
        bot.reply_to(message, "По '" + keyword + "' ничего нет.")
        return

    lines = ["Найдено " + str(len(results)) + " по '" + keyword + "':\n"]
    for jid, ch, cat, title, desc, url in results:
        lines.append("#" + str(jid) + " [" + cat + "] " + title)
        lines.append("   " + desc[:120] + "...")
        lines.append("   " + url + "\n")
    send_code(message, "\n".join(lines))


@bot.message_handler(commands=['stats'])
def handle_stats_bot(message):
    """Быстрая статистика бота."""
    try:
        s = get_quick_stats()
        lines = [
            "📊 Статистика бота",
            "",
            "📋 Всего вакансий: " + str(s["total"]),
            "📅 За сегодня: " + str(s["today"]),
            "📆 За 7 дней: " + str(s["week"]),
            "📤 Отправлено тебе: " + str(s["sent"]),
            "",
            "📦 Проектов: " + str(s["projects"]) + " (" + str(s["zips"]) + " ZIP)",
            "",
            "🏆 Топ-каналы:",
        ]
        for ch, cnt in s["top_channels"]:
            lines.append("  @" + ch + " — " + str(cnt))
        lines.append("")
        lines.append("🌐 Дашборд: https://ai-freelancer-bot.onrender.com/dashboard")
        bot.reply_to(message, "\n".join(lines))
    except Exception as e:
        import traceback
        bot.reply_to(message, "Ошибка: " + traceback.format_exc()[-300:])




@bot.message_handler(commands=['track'])
def handle_track(message):
    """Сохраняет фильтр. Поддерживает: слова, -исключения, lang:en/ru"""
    keywords = message.text.replace("/track", "", 1).strip()
    if not keywords:
        bot.reply_to(
            message,
            "Формат: /track python, бот, -java, lang:ru\n\n"
            "Что можно:\n"
            "• python, бот — что искать\n"
            "• -java, -php — что исключить\n"
            "• lang:en / lang:ru — язык вакансий"
        )
        return

    user_id = message.from_user.id
    set_filter(user_id, keywords)

    f = parse_filter_keywords(keywords)
    parts = []
    if f["include"]:
        parts.append("Ищу: " + " | ".join(f["include"]))
    if f["exclude"]:
        parts.append("Исключаю: " + " | ".join(f["exclude"]))
    if f["lang"]:
        parts.append("Язык: " + f["lang"])

    bot.reply_to(message, "✅ Фильтр сохранён:\n" + "\n".join(parts))


@bot.message_handler(commands=['untrack'])
def handle_untrack(message):
    """Отключает фильтр."""
    user_id = message.from_user.id
    clear_filter(user_id)
    bot.reply_to(message, "🛑 Фильтр отключён. Больше не буду присылать автоподборки.")


@bot.message_handler(commands=['myfilter'])
def handle_myfilter(message):
    """Показывает текущий фильтр."""
    user_id = message.from_user.id
    keywords = get_filter(user_id)
    if not keywords:
        bot.reply_to(message, "У тебя нет фильтра. Задай через /track python, веб")
        return
    words = [w.strip() for w in keywords.split(",")]
    bot.reply_to(message, f"🎯 Твой фильтр:\n🔍 {' | '.join(words)}")


# ============================================================
# МОДУЛЬ ГЕНЕРАЦИИ ПРОЕКТОВ ДЛЯ КЛИЕНТОВ
# ============================================================

import io  # для передачи файла в Telegram

TYPE_NAMES = {"bot": "Telegram-бот", "parser": "Парсер", "automate": "Автоматизация"}
TYPE_FILES = {"bot": "bot.py", "parser": "parser.py", "automate": "automate.py"}


def _handle_make(message, project_type):
    """Общая логика для /make_bot, /make_parser, /automate."""
    cmd = message.text.split()[0]  # /make_bot и т.п.
    tz = message.text.replace(cmd, "", 1).strip()

    if len(tz) < 15:
        bot.reply_to(message, f"⚠ Опиши подробнее, что нужно.\nПример: {cmd} сделай бота для кофейни с меню и оплатой")
        return

    bot.reply_to(message, f"🧠 Генерирую {TYPE_NAMES[project_type]}... Это займёт 20-60 сек.")

    try:
        code = generate_project(tz, project_type)
        if not code:
            bot.reply_to(message, "⚠ ИИ не смог сгенерировать проект. Попробуй позже.")
            return

        user_id = message.from_user.id
        pid = save_project(user_id, project_type, tz, code)

        # 1. Отправляем файл
        file_name = TYPE_FILES[project_type]
        file_bytes = io.BytesIO(code.encode("utf-8"))
        file_bytes.name = file_name
        bot.send_document(
            message.chat.id,
            file_bytes,
            visible_file_name=file_name,
            caption=f"✅ {TYPE_NAMES[project_type]} готов!\n🆔 Проект #{pid}\n\nСкачать повторно: /download {pid}"
        )

        # 2. Превью кода
        preview = code[:800]
        bot.send_message(message.chat.id, f"👀 Превью:\n\n{preview}...")

    except Exception as e:
        import traceback
        bot.reply_to(message, f"🔥 Ошибка: {traceback.format_exc()[-300:]}")


@bot.message_handler(commands=['make_bot'])
def handle_make_bot(message):
    _handle_make(message, "bot")


@bot.message_handler(commands=['make_parser'])
def handle_make_parser(message):
    _handle_make(message, "parser")


@bot.message_handler(commands=['automate'])
def handle_automate(message):
    _handle_make(message, "automate")


@bot.message_handler(commands=['projects'])
def handle_projects(message):
    """Список проектов клиента."""
    user_id = message.from_user.id
    rows = get_user_projects(user_id, limit=10)
    if not rows:
        bot.reply_to(message, "У тебя пока нет проектов.\nСоздай первый: /make_bot, /make_parser или /automate")
        return
    lines = ["📦 Твои проекты:\n"]
    for pid, ptype, tz, created in rows:
        short_tz = tz[:50] + ("..." if len(tz) > 50 else "")
        lines.append(f"#{pid} [{TYPE_NAMES.get(ptype, ptype)}] {short_tz}\n    📅 {created}")
    lines.append("\nСкачать: /download <id>")
    bot.reply_to(message, "\n".join(lines))


@bot.message_handler(commands=['download'])
def handle_download(message):
    """Скачать проект повторно по id."""
    try:
        pid = int(message.text.replace("/download", "", 1).strip())
    except ValueError:
        bot.reply_to(message, "Укажи ID. Пример: /download 5")
        return

    user_id = message.from_user.id
    row = get_project(pid, user_id)
    if not row:
        bot.reply_to(message, f"❌ Проект #{pid} не найден.")
        return

    ptype, tz, code = row
    file_name = TYPE_FILES.get(ptype, "project.py")
    file_bytes = io.BytesIO(code.encode("utf-8"))
    file_bytes.name = file_name
    bot.send_document(message.chat.id, file_bytes, visible_file_name=file_name,
                      caption=f"📦 Проект #{pid} [{TYPE_NAMES.get(ptype, ptype)}]")


@bot.message_handler(commands=['edit'])
def handle_edit(message):
    """Дорабатывает существующий проект: /edit <id> <правки>."""
    try:
        text = message.text.replace("/edit", "", 1).strip()
        if not text:
            bot.reply_to(message, "Формат: /edit <id> <правки>\nПример: /edit 5 добавь команду /menu")
            return

        parts = text.split(maxsplit=1)
        try:
            pid = int(parts[0])
        except ValueError:
            bot.reply_to(message, "Укажи числовой ID. Пример: /edit 5 добавь /menu")
            return

        if len(parts) < 2 or len(parts[1]) < 5:
            bot.reply_to(message, "Опиши правки после ID. Пример: /edit 5 добавь inline-кнопки")
            return

        tz_edit = parts[1]
        user_id = message.from_user.id
        row = get_project_with_parent(pid, user_id)
        if not row:
            bot.reply_to(message, "Проект #" + str(pid) + " не найден.")
            return

        old_id, ptype, old_tz, old_code, parent_id = row
        bot.reply_to(message, "Дорабатываю проект #" + str(pid) + "... 20-60 сек.")

        new_code = edit_project(old_code, tz_edit, ptype)
        if not new_code:
            bot.reply_to(message, "ИИ не смог доработать. Попробуй позже.")
            return

        new_id = save_project(user_id, ptype, "[ред. #" + str(pid) + "] " + tz_edit, new_code, parent_id=pid)

        file_name = TYPE_FILES.get(ptype, "project.py")
        file_bytes = io.BytesIO(new_code.encode("utf-8"))
        file_bytes.name = file_name
        bot.send_document(
            message.chat.id,
            file_bytes,
            visible_file_name=file_name,
            caption="✅ Новая версия #" + str(new_id) + " (от #" + str(pid) + ")\nСкачать: /download " + str(new_id)
        )

    except Exception as e:
        import traceback
        bot.reply_to(message, "Ошибка: " + traceback.format_exc()[-300:])


# ============================================================
# МНОГОФАЙЛОВЫЕ ПРОЕКТЫ (ZIP-АРХИВЫ)
# ============================================================

import zipfile

def _detect_project_type(tz):
    """Определяет тип проекта по ключевым словам в ТЗ."""
    low = tz.lower()
    if any(w in low for w in ["парс", "scrap", "спарси", "собрать данные"]):
        return "parser"
    if any(w in low for w in ["бот", "bot", "телеграм", "telegram"]):
        return "bot"
    return "automate"


def _make_zip(files_dict):
    """Создаёт ZIP-архив из dict {filename: code}. Возвращает io.BytesIO."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, code in files_dict.items():
            zf.writestr(name, code)
    buf.seek(0)
    return buf


@bot.message_handler(commands=['make_full'])
def handle_make_full(message):
    """Генерирует многофайловый проект и отправляет ZIP-архив."""
    tz = message.text.replace("/make_full", "", 1).strip()
    if len(tz) < 15:
        bot.reply_to(message, "Опиши подробнее. Пример: /make_full бот для кофейни с меню и оплатой")
        return

    ptype = _detect_project_type(tz)

    # Проверяем, есть ли у клиента загруженный файл — используем как доп. ТЗ
    user_id = message.from_user.id
    file_row = get_latest_user_file(user_id)
    if file_row:
        filename, file_content, _, _ = file_row
        tz = tz + "\n\n=== ДОП. ТЗ ИЗ ФАЙЛА " + filename + " ===\n" + file_content[:8000]
        bot.reply_to(message, "📎 Учту содержимое файла " + filename)

    bot.reply_to(message, "🧠 Генерирую многофайловый проект (" + ptype + ")... 40-90 сек.")

    try:
        files = generate_full_project(tz, ptype)
        if not files:
            bot.reply_to(message, "⚠ ИИ не смог сгенерировать проект.")
            return

        user_id = message.from_user.id
        pid = save_full_project(user_id, tz, files)

        # Sandbox-проверка главного файла (если есть)
        main_file = None
        for name in ["bot.py", "main.py"]:
            if name in files:
                main_file = name
                break

        test_report = ""
        if main_file:
            try:
                from sandbox import test_project_safe
                r = test_project_safe(files, main_file, timeout=15)
                if r["ok"]:
                    test_report = "\n\n✅ Sandbox: код запустился без ошибок"
                else:
                    err = (r.get("error") or r.get("stderr", ""))[:200]
                    test_report = "\n\n⚠ Sandbox обнаружил проблему:\n" + err
            except Exception as e:
                test_report = "\n\n⚠ Sandbox не сработал: " + str(e)[:100]

        # Формируем краткое резюме
        file_list = "\n".join(["  • " + n for n in sorted(files.keys())])
        zip_buf = _make_zip(files)
        zip_name = "project_" + str(pid) + ".zip"

        bot.send_document(
            message.chat.id,
            zip_buf,
            visible_file_name=zip_name,
            caption="✅ Многофайловый проект #" + str(pid) + " готов!\n\n📁 Файлы:\n" + file_list + test_report + "\n\nСкачать: /dl_full " + str(pid) + "\nТест: /test " + str(pid)
        )
    except Exception as e:
        import traceback
        bot.reply_to(message, "🔥 Ошибка: " + traceback.format_exc()[-300:])


@bot.message_handler(commands=['myfulls'])
def handle_myfulls(message):
    """Список многофайловых проектов."""
    user_id = message.from_user.id
    rows = get_user_full_projects(user_id, limit=10)
    if not rows:
        bot.reply_to(message, "У тебя нет многофайловых проектов.\nСоздай: /make_full бот для ...")
        return
    lines = ["📦 Твои ZIP-проекты:\n"]
    for pid, tz, created in rows:
        short_tz = tz[:60] + ("..." if len(tz) > 60 else "")
        lines.append("#" + str(pid) + " " + short_tz + "\n    📅 " + created)
    lines.append("\nСкачать: /dl_full <id>")
    bot.reply_to(message, "\n".join(lines))


@bot.message_handler(commands=['dl_full'])
def handle_dl_full(message):
    """Скачать ZIP-проект по id."""
    try:
        pid = int(message.text.replace("/dl_full", "", 1).strip())
    except ValueError:
        bot.reply_to(message, "Укажи ID. Пример: /dl_full 3")
        return

    user_id = message.from_user.id
    files = get_full_project(pid, user_id)
    if not files:
        bot.reply_to(message, "❌ Проект #" + str(pid) + " не найден.")
        return

    zip_buf = _make_zip(files)
    file_list = "\n".join(["  • " + n for n in sorted(files.keys())])
    bot.send_document(
        message.chat.id,
        zip_buf,
        visible_file_name="project_" + str(pid) + ".zip",
        caption="📦 Проект #" + str(pid) + "\n\n📁 Файлы:\n" + file_list
    )


# ============================================================
# АВТОДЕПЛОЙ НА GITHUB + RENDER
# ============================================================

from deployer import deploy_project

import time


def _safe_repo_name(pid, ptype):
    """Генерирует безопасное имя репозитория."""
    return "aifreelancer-" + ptype + "-" + str(pid) + "-" + str(int(time.time()))


@bot.message_handler(commands=['deploy'])
def handle_deploy(message):
    """Деплоит проект на GitHub + даёт ссылку на Render."""
    try:
        text = message.text.replace("/deploy", "", 1).strip()
        if not text:
            bot.reply_to(message, "Формат: /deploy <id>\nПример: /deploy 5\n(работает для /make_full проектов)")
            return

        try:
            pid = int(text.split()[0])
        except ValueError:
            bot.reply_to(message, "Укажи ID. Пример: /deploy 5")
            return

        user_id = message.from_user.id
        files = get_full_project(pid, user_id)
        if not files:
            bot.reply_to(message, "Проект #" + str(pid) + " не найден среди многофайловых.\nСначала создай через /make_full.")
            return

        bot.reply_to(message, "🚀 Деплою на GitHub... Это займёт 10-30 сек.")

        rows = get_user_full_projects(user_id, limit=20)
        tz = "проект"
        ptype = "bot"
        for fid, ftz, _ in rows:
            if fid == pid:
                tz = ftz
                break

        if any("bot.py" in k for k in files.keys()):
            ptype = "bot"
        elif any("parser.py" in k for k in files.keys()):
            ptype = "parser"
        else:
            ptype = "automate"

        repo_name = _safe_repo_name(pid, ptype)
        result = deploy_project(repo_name, files, tz, ptype)

        if not result["ok"]:
            bot.reply_to(message, "❌ Ошибка деплоя: " + result["error"])
            return

        lines = [
            "✅ Проект загружен на GitHub!",
            "",
            "📦 Репозиторий:",
            result["repo_url"],
            "",
            "🚀 Deploy to Render (одна кнопка):",
            result["deploy_url"],
            "",
            "📋 Что делать:",
            "1. Открой ссылку Deploy to Render",
            "2. Авторизуйся в Render (если нужно)",
            "3. Введи BOT_TOKEN от @BotFather",
            "4. Дождись билда (~2 мин)",
            "",
            "📁 Файлов загружено: " + str(result["uploaded"]) + "/" + str(result["total"]),
        ]
        bot.reply_to(message, "\n".join(lines))

    except Exception as e:
        import traceback
        bot.reply_to(message, "🔥 Ошибка: " + traceback.format_exc()[-300:])


@bot.message_handler(commands=['notes'])
def handle_notes(message):
    """Список заметок юзера. /notes или /notes add <id> <текст>"""
    user_id = message.from_user.id
    text = message.text.replace("/notes", "", 1).strip()

    # /notes add <id> <текст>
    if text.startswith("add "):
        parts = text[4:].split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(message, "Формат: /notes add <job_id> <текст>")
            return
        try:
            jid = int(parts[0])
        except ValueError:
            bot.reply_to(message, "job_id должен быть числом")
            return
        note_text = parts[1]
        save_note(user_id, jid, note_text)
        bot.reply_to(message, "✅ Заметка сохранена для #" + str(jid))
        return

    # /notes — список
    notes = get_user_notes(user_id, limit=20)
    if not notes:
        bot.reply_to(message, "Заметок нет. Формат: /notes add <job_id> <текст>")
        return
    user_id = message.from_user.id
    lines = ["📝 Твои заметки:\n"]
    for jid, note, created, title, url in notes:
        short_title = (title or "?")[:60]
        st = get_job_status(user_id, jid)
        icon = STATUS_ICONS.get(st[0], "⚪") if st else "⚪"
        lines.append(icon + " #" + str(jid) + " " + short_title)
        lines.append("   💬 " + note)
        lines.append("   📅 " + created + "\n")
    bot.reply_to(message, "\n".join(lines))


@bot.message_handler(commands=['apply'])
def handle_apply(message):
    """Генерирует черновик письма клиенту. /apply <job_id>"""
    try:
        jid = int(message.text.replace("/apply", "", 1).strip())
    except ValueError:
        bot.reply_to(message, "Формат: /apply <job_id>. Пример: /apply 5")
        return

    row = get_job_by_id(jid)
    if not row:
        bot.reply_to(message, "Вакансия #" + str(jid) + " не найдена.")
        return

    _, channel, category, title, description, url = row
    bot.reply_to(message, "Пишу черновик письма... 15-30 сек.")

    draft = generate_apply_draft(title, description, category)
    if not draft:
        bot.reply_to(message, "Не получилось сгенерировать.")
        return

    # Ставим статус "в работе" — ты уже готовишь отклик
    user_id = message.from_user.id
    set_job_status(user_id, jid, "in_work")

    text = (
        "Черновик для #" + str(jid) + " (статус: 🟡 в работе)\n\n" +
        draft + "\n\n" +
        "Ссылка на вакансию: " + url + "\n\n" +
        "Сменить статус: /status " + str(jid) + " <new|in_work|won|lost|archived>"
    )
    send_code(message, text)


@bot.message_handler(commands=['budget'])
def handle_budget(message):
    """Оценивает бюджет вакансии. /budget <job_id>"""
    try:
        jid = int(message.text.replace("/budget", "", 1).strip())
    except ValueError:
        bot.reply_to(message, "Формат: /budget <job_id>. Пример: /budget 5")
        return

    row = get_job_by_id(jid)
    if not row:
        bot.reply_to(message, "Вакансия #" + str(jid) + " не найдена.")
        return

    _, channel, category, title, description, url = row
    bot.reply_to(message, "Оцениваю бюджет...")

    verdict, reason = evaluate_budget(title, description, category)
    icons = {"adequate": "✅ Адекватно", "low": "⚠ Мало", "high": "🎉 Хорошо", "unclear": "❓ Не указан"}
    label = icons.get(verdict, "❓ " + verdict)

    bot.reply_to(message,
        "💰 Бюджет #" + str(jid) + "\n\n" +
        "Оценка: " + label + "\n" +
        ("Причина: " + reason + "\n\n" if reason else "\n") +
        "Вакансия: " + title[:100] + "\n" +
        "Ссылка: " + url
    )


STATUS_ICONS = {
    "new": "🔵",
    "in_work": "🟡",
    "won": "🟢",
    "lost": "🔴",
    "archived": "⚫",
}

STATUS_NAMES = {
    "new": "новая",
    "in_work": "в работе",
    "won": "получен",
    "lost": "отказ",
    "archived": "архив",
}


@bot.message_handler(commands=['status'])
def handle_status(message):
    """Меняет статус вакансии. /status <job_id> <new|in_work|won|lost|archived>"""
    parts = message.text.replace("/status", "", 1).strip().split()
    if len(parts) < 2:
        bot.reply_to(message, "Формат: /status <id> <new|in_work|won|lost|archived>\nПример: /status 5 won")
        return

    try:
        jid = int(parts[0])
    except ValueError:
        bot.reply_to(message, "job_id должен быть числом")
        return

    new_status = parts[1].lower()
    if new_status not in STATUS_NAMES:
        bot.reply_to(message, "Статус должен быть: new / in_work / won / lost / archived")
        return

    user_id = message.from_user.id
    row = get_job_by_id(jid)
    if not row:
        bot.reply_to(message, "Вакансия #" + str(jid) + " не найдена")
        return

    set_job_status(user_id, jid, new_status)
    icon = STATUS_ICONS[new_status]
    bot.reply_to(message, icon + " Статус #" + str(jid) + " → " + STATUS_NAMES[new_status])


@bot.message_handler(commands=['myjobs'])
def handle_myjobs(message):
    """Показывает вакансии в работе (или с другим статусом)."""
    text = message.text.replace("/myjobs", "", 1).strip().lower()
    status_filter = text if text in STATUS_NAMES else "in_work"

    user_id = message.from_user.id
    rows = get_jobs_by_status(user_id, status=status_filter, limit=20)

    if not rows:
        bot.reply_to(message, "Нет вакансий со статусом '" + STATUS_NAMES.get(status_filter, status_filter) + "'.\nМеняй через /status <id> won/lost/in_work")
        return

    icon = STATUS_ICONS.get(status_filter, "⚪")
    lines = [icon + " Вакансии (" + STATUS_NAMES.get(status_filter, status_filter) + "): " + str(len(rows)) + "\n"]
    for jid, st, updated, title, url in rows:
        short_title = (title or "?")[:60]
        lines.append("#" + str(jid) + " " + short_title)
        lines.append("   📅 " + (updated or "")[:16])
    lines.append("\nМенять статус: /status <id> <new|in_work|won|lost|archived>")
    bot.reply_to(message, "\n".join(lines))


@bot.message_handler(commands=['statuses'])
def handle_statuses_summary(message):
    """Сводка по всем статусам."""
    user_id = message.from_user.id
    lines = ["📊 Сводка по статусам:\n"]
    total = 0
    for st in ["new", "in_work", "won", "lost", "archived"]:
        rows = get_jobs_by_status(user_id, status=st, limit=999)
        cnt = len(rows)
        total += cnt
        lines.append(STATUS_ICONS[st] + " " + STATUS_NAMES[st] + ": " + str(cnt))
    lines.append("\nВсего отмечено: " + str(total))
    lines.append("\nКоманды: /myjobs, /status <id> <st>")
    bot.reply_to(message, "\n".join(lines))


@bot.message_handler(commands=['test'])
def handle_test_code(message):
    """Тестирует сгенерированный проект в sandbox. /test <id>"""
    try:
        pid = int(message.text.replace("/test", "", 1).strip())
    except ValueError:
        bot.reply_to(message, "Формат: /test <id>. Пример: /test 8")
        return

    user_id = message.from_user.id
    files = get_full_project(pid, user_id)
    if not files:
        bot.reply_to(message, "Проект #" + str(pid) + " не найден среди многофайловых.")
        return

    # Ищем главный файл
    main_file = None
    for name in ["bot.py", "main.py"]:
        if name in files:
            main_file = name
            break
    if not main_file:
        bot.reply_to(message, "В проекте нет bot.py или main.py — нечего тестировать.")
        return

    bot.reply_to(message, "Запускаю sandbox-тест...")

    # Импорт только здесь
    from sandbox import test_project_safe

    result = test_project_safe(files, main_file, timeout=15)

    if result["ok"]:
        out = result["stdout"].strip()[:500] or "(нет вывода)"
        bot.reply_to(message,
            "✅ Тест #" + str(pid) + " пройден\n\n"
            "Файл: " + main_file + "\n\n"
            "Вывод:\n" + out
        )
    else:
        err = result.get("error") or result.get("stderr", "")[:500]
        bot.reply_to(message,
            "❌ Тест #" + str(pid) + " провален\n\n"
            "Ошибка:\n" + err
        )


# ============================================================
# ПРИЁМ ФАЙЛОВ ОТ КЛИЕНТА
# ============================================================

@bot.message_handler(content_types=['document'])
def handle_document(message):
    """Принимает документ от клиента и извлекает из него текст."""
    try:
        doc = message.document
        filename = doc.file_name or "file"
        file_size = doc.file_size or 0

        # Лимит 5 МБ
        if file_size > 5 * 1024 * 1024:
            bot.reply_to(message, "⚠ Файл больше 5 МБ. Пришли поменьше.")
            return

        bot.reply_to(message, "📥 Скачиваю " + filename + "...")

        # Скачиваем файл из Telegram
        file_info = bot.get_file(doc.file_id)
        downloaded = bot.download_file(file_info.file_path)

        # Парсим
        from file_parser import extract_text
        text, err = extract_text(downloaded, filename)

        if err:
            bot.reply_to(message, "❌ " + err)
            return

        # Сохраняем в БД
        user_id = message.from_user.id
        file_type = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"
        save_user_file(user_id, filename, text, file_type)

        preview = text[:400].replace("\n", " ")
        bot.reply_to(message,
            "✅ Файл принят: " + filename + "\n"
            "📏 Извлечено: " + str(len(text)) + " символов\n\n"
            "Превью:\n" + preview + "...\n\n"
            "Теперь пиши /make_full <ТЗ> — бот учтёт содержимое файла."
        )
    except Exception as e:
        import traceback
        bot.reply_to(message, "🔥 Ошибка приёма: " + traceback.format_exc()[-300:])


@bot.message_handler(commands=['clearfile'])
def handle_clearfile(message):
    """Удаляет последний файл юзера."""
    user_id = message.from_user.id
    clear_user_files(user_id)
    bot.reply_to(message, "🗑 Файлы удалены. Следующий /make_full будет без них.")


@bot.message_handler(commands=['myfile'])
def handle_myfile(message):
    """Показывает, какой файл сейчас сохранён."""
    user_id = message.from_user.id
    row = get_latest_user_file(user_id)
    if not row:
        bot.reply_to(message, "📂 Нет сохранённых файлов. Отправь документ.")
        return
    filename, content, ftype, uploaded = row
    preview = content[:300].replace("\n", " ")
    bot.reply_to(message,
        "📄 Последний файл: " + filename + "\n"
        "Тип: " + ftype + "\n"
        "Загружен: " + uploaded + "\n"
        "Размер: " + str(len(content)) + " символов\n\n"
        "Превью:\n" + preview + "..."
    )
