"""Обработчики команд для профи Python-разработчика."""

import html
import io
import zipfile

from core import bot
from config import TELEGRAM_MAX_LEN, MAX_ATTEMPTS
from database import (
    save_user, get_user_stats, get_all_clients,
    save_project, get_user_projects, get_project, get_project_with_parent,
    save_full_project, get_user_full_projects, get_full_project,
    save_task, update_task, get_user_tasks,
    save_user_file, get_latest_user_file, clear_user_files,
)
from frontend import generate_single_page, generate_full_landing
from selenium_gen import generate_js_parser
from integrations import generate_integration, SERVICES
from rag import find_similar_projects, save_embedding, backfill_embeddings
from ai import (
    ask_ai, run_code, auto_fix,
    generate_project, edit_project, generate_full_project,
    review_code, explain_code, fix_code,
    generate_tests, architect_project, refactor_code,
    set_model, get_current_model,
)


TYPE_NAMES = {"bot": "Telegram-бот", "parser": "Парсер", "automate": "Автоматизация"}
TYPE_FILES = {"bot": "bot.py", "parser": "parser.py", "automate": "automate.py"}


# ============================================================
# УТИЛИТЫ
# ============================================================

def split_long_message(text, max_len=None):
    """Режет длинный текст на куски по max_len символов."""
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
            bot.reply_to(message, f"\u26A0 Не смог отправить: {e}")


def _detect_project_type(tz):
    """Определяет тип проекта по ключевым словам в ТЗ."""
    low = tz.lower()
    if any(w in low for w in ["парс", "scrap", "спарси", "собрать данные"]):
        return "parser"
    if any(w in low for w in ["бот", "bot", "телеграм", "telegram"]):
        return "bot"
    return "automate"


def _make_zip(files_dict):
    """Создаёт ZIP-архив из dict {filename: code}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, code in files_dict.items():
            zf.writestr(name, code)
    buf.seek(0)
    return buf


# ============================================================
# БАЗОВЫЕ КОМАНДЫ
# ============================================================

@bot.message_handler(commands=['start'])
def send_welcome(message):
    """Регистрирует пользователя и показывает меню."""
    user_id = message.from_user.id
    username = message.from_user.first_name or message.from_user.username or "разработчик"
    save_user(user_id, username)
    bot.reply_to(message,
        f"Привет, {username}! Я AI Python-разработчик.\n\n"
        "Основные команды:\n"
        "/code <ТЗ> — сгенерировать код\n"
        "/run <ТЗ> — сгенерировать и выполнить\n"
        "/make_bot <ТЗ> — Telegram-бот\n"
        "/make_parser <ТЗ> — парсер\n"
        "/make_full <ТЗ> — ZIP-проект с тестами\n"
        "/edit <id> <правки> — доработать\n"
        "/projects — список проектов\n"
        "/test <id> — проверить в sandbox\n"
        "/deploy <id> — деплой на Render\n\n"
        "/help — все команды"
    )


@bot.message_handler(commands=['help'])
def send_help(message):
    """Показывает список команд."""
    current_model = get_current_model()
    bot.reply_to(message,
        "📚 Команды разработчика:\n\n"
        "🐍 Python: /code, /run, /make_bot, /make_parser, /automate, /make_full\n\n"
        "🌐 Frontend: /make_site, /make_landing\n\n"
        "🕷 JS-парсеры: /make_js_parser\n\n"
        "🔌 Интеграции: /integrate <сервис> <ТЗ>\n"
        "   Сервисы: stars, yookassa, stripe, amocrm, gsheets, openai\n\n"
        "🔍 Работа с кодом: /review, /explain, /fix, /tests, /refactor, /architect\n\n"
        "🧠 Память: /find_project, /similar, /reindex\n\n"
        "🧠 Модель: /model [lite|pro|latest]\n\n"
        "🔨 Проекты: /projects, /download, /dl_full, /edit, /test, /deploy\n\n"
        "📎 Файлы: PDF/TXT → ТЗ, /myfile, /clearfile\n\n"
        f"Текущая модель: {current_model}"
    )

def handle_stats(message):
    """Показывает статистику юзера."""
    user_id = message.from_user.id
    stats = get_user_stats(user_id)
    if stats is None:
        bot.reply_to(message, "Ты ещё не в базе. Напиши /start!")
        return
    username, first_seen, count = stats
    bot.reply_to(message,
        f"📊 Статистика:\n"
        f"👤 Имя: {username}\n"
        f"📅 Первый раз: {first_seen}\n"
        f"✉️ Сообщений: {count}"
    )


@bot.message_handler(commands=['clients'])
def handle_clients(message):
    """Показывает всех юзеров бота."""
    rows = get_all_clients()
    if not rows:
        bot.reply_to(message, "Юзеров пока нет.")
        return
    lines = [f"👥 Всего: {len(rows)}\n"]
    for i, row in enumerate(rows, start=1):
        _, username, first_seen, count = row
        lines.append(f"{i}. {username} — {count} сообщ.")
    bot.reply_to(message, "\n".join(lines))


# ============================================================
# ГЕНЕРАЦИЯ КОДА
# ============================================================

@bot.message_handler(commands=['code'])
def handle_code(message):
    """Генерирует код по текстовому заданию (без выполнения)."""
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
            bot.reply_to(message, "Напиши задание. Пример: /run посчитай сумму 1..100")
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
    """Показывает последние 5 задач юзера."""
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


# ============================================================
# ГЕНЕРАЦИЯ ПРОЕКТОВ
# ============================================================

def _handle_make(message, project_type):
    """Общая логика для /make_bot, /make_parser, /automate."""
    cmd = message.text.split()[0]
    tz = message.text.replace(cmd, "", 1).strip()

    if len(tz) < 10:
        bot.reply_to(message, f"Опиши подробнее.\nПример: {cmd} сделай бота для кафе")
        return

    bot.reply_to(message, f"🧠 Генерирую {TYPE_NAMES[project_type]}... 20-60 сек.")

    try:
        code = generate_project(tz, project_type)
        if not code:
            bot.reply_to(message, "⚠ ИИ не смог сгенерировать проект. Попробуй позже.")
            return

        user_id = message.from_user.id
        pid = save_project(user_id, project_type, tz, code)

        # Автоматически считаем embedding для RAG-поиска
        try:
            from rag import save_embedding
            save_embedding(pid, project_type, tz + chr(10) + code[:1000])
        except Exception as ee:
            print("embed error: " + str(ee)[:150], flush=True)

        file_name = TYPE_FILES[project_type]
        file_bytes = io.BytesIO(code.encode("utf-8"))
        file_bytes.name = file_name
        bot.send_document(
            message.chat.id,
            file_bytes,
            visible_file_name=file_name,
            caption=f"✅ {TYPE_NAMES[project_type]} готов!\n🆔 Проект #{pid}\n\nСкачать: /download {pid}"
        )
        preview = code[:600]
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


@bot.message_handler(commands=['make_full'])
def handle_make_full(message):
    """Генерирует многофайловый проект и отправляет ZIP."""
    tz = message.text.replace("/make_full", "", 1).strip()
    if len(tz) < 10:
        bot.reply_to(message, "Опиши подробнее. Пример: /make_full бот для кофейни с меню")
        return

    ptype = _detect_project_type(tz)
    bot.reply_to(message, f"🧠 Генерирую многофайловый проект ({ptype})... 40-90 сек.")

    try:
        files = generate_full_project(tz, ptype)
        if not files:
            bot.reply_to(message, "⚠ ИИ не смог сгенерировать проект.")
            return

        user_id = message.from_user.id
        pid = save_full_project(user_id, tz, files)

        # Автоматически считаем embedding для RAG-поиска
        try:
            from rag import save_embedding
            code_all = chr(10).join(files.values())[:1000]
            save_embedding(pid, ptype, tz + chr(10) + code_all)
        except Exception as ee:
            print("embed error: " + str(ee)[:150], flush=True)

        # Sandbox-проверка
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

        file_list = "\n".join(["  • " + n for n in sorted(files.keys())])
        zip_buf = _make_zip(files)
        zip_name = f"project_{pid}.zip"

        bot.send_document(
            message.chat.id,
            zip_buf,
            visible_file_name=zip_name,
            caption=(f"✅ Многофайловый проект #{pid} готов!\n\n"
                     f"📁 Файлы:\n{file_list}{test_report}\n\n"
                     f"Скачать: /dl_full {pid}\nТест: /test {pid}")
        )
    except Exception as e:
        import traceback
        bot.reply_to(message, f"🔥 Ошибка: {traceback.format_exc()[-300:]}")


@bot.message_handler(commands=['edit'])
def handle_edit(message):
    """Дорабатывает существующий проект: /edit <id> <правки>."""
    try:
        text = message.text.replace("/edit", "", 1).strip()
        if not text:
            bot.reply_to(message, "Формат: /edit <id> <правки>\nПример: /edit 5 добавь /menu")
            return

        parts = text.split(maxsplit=1)
        try:
            pid = int(parts[0])
        except ValueError:
            bot.reply_to(message, "Укажи числовой ID. Пример: /edit 5 добавь /menu")
            return

        if len(parts) < 2 or len(parts[1]) < 5:
            bot.reply_to(message, "Опиши правки после ID.")
            return

        tz_edit = parts[1]
        user_id = message.from_user.id
        row = get_project_with_parent(pid, user_id)
        if not row:
            bot.reply_to(message, f"❌ Проект #{pid} не найден.")
            return

        old_id, ptype, old_tz, old_code, parent_id = row
        bot.reply_to(message, f"🧠 Дорабатываю проект #{pid}... 20-60 сек.")

        new_code = edit_project(old_code, tz_edit, ptype)
        if not new_code:
            bot.reply_to(message, "⚠ ИИ не смог доработать.")
            return

        new_id = save_project(user_id, ptype, f"[ред. #{pid}] {tz_edit}", new_code, parent_id=pid)

        file_name = TYPE_FILES.get(ptype, "project.py")
        file_bytes = io.BytesIO(new_code.encode("utf-8"))
        file_bytes.name = file_name
        bot.send_document(
            message.chat.id,
            file_bytes,
            visible_file_name=file_name,
            caption=f"✅ Новая версия #{new_id} (от #{pid})\nСкачать: /download {new_id}"
        )
    except Exception as e:
        import traceback
        bot.reply_to(message, f"🔥 Ошибка: {traceback.format_exc()[-300:]}")


# ============================================================
# ПРОЕКТЫ
# ============================================================

@bot.message_handler(commands=['projects'])
def handle_projects(message):
    """Список однофайловых проектов."""
    user_id = message.from_user.id
    rows = get_user_projects(user_id, limit=10)
    if not rows:
        bot.reply_to(message, "Проектов нет. Создай: /make_bot, /make_parser или /automate")
        return
    lines = ["📦 Твои проекты:\n"]
    for pid, ptype, tz, created in rows:
        short_tz = tz[:50] + ("..." if len(tz) > 50 else "")
        lines.append(f"#{pid} [{TYPE_NAMES.get(ptype, ptype)}] {short_tz}\n    📅 {created}")
    lines.append("\nСкачать: /download <id>")
    bot.reply_to(message, "\n".join(lines))


@bot.message_handler(commands=['download'])
def handle_download(message):
    """Скачать однофайловый проект по id."""
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


@bot.message_handler(commands=['myfulls'])
def handle_myfulls(message):
    """Список ZIP-проектов."""
    user_id = message.from_user.id
    rows = get_user_full_projects(user_id, limit=10)
    if not rows:
        bot.reply_to(message, "Нет многофайловых проектов. Создай: /make_full бот для ...")
        return
    lines = ["📦 Твои ZIP-проекты:\n"]
    for pid, tz, created in rows:
        short_tz = tz[:60] + ("..." if len(tz) > 60 else "")
        lines.append(f"#{pid} {short_tz}\n    📅 {created}")
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
        bot.reply_to(message, f"❌ Проект #{pid} не найден.")
        return
    zip_buf = _make_zip(files)
    file_list = "\n".join(["  • " + n for n in sorted(files.keys())])
    bot.send_document(message.chat.id, zip_buf, visible_file_name=f"project_{pid}.zip",
                      caption=f"📦 Проект #{pid}\n\n📁 Файлы:\n{file_list}")


@bot.message_handler(commands=['test'])
def handle_test_code(message):
    """Тестирует проект в sandbox (по возможности — pytest)."""
    try:
        pid = int(message.text.replace("/test", "", 1).strip())
    except ValueError:
        bot.reply_to(message, "Формат: /test <id>. Пример: /test 5")
        return

    user_id = message.from_user.id
    files = get_full_project(pid, user_id)
    if not files:
        bot.reply_to(message, f"Проект #{pid} не найден среди многофайловых.")
        return

    # Ищем тестовые файлы
    test_files = [n for n in files.keys() if n.startswith("test_") and n.endswith(".py")]

    bot.reply_to(message, "🧪 Запускаю тесты...")

    if test_files:
        from sandbox import run_pytest
        result = run_pytest(files, timeout=30)
        if result["ok"]:
            bot.reply_to(message,
                f"✅ Тесты #{pid} пройдены!\n📊 {result['summary'] or 'все ок'}"
            )
        else:
            bot.reply_to(message,
                f"❌ Тесты #{pid} упали.\n"
                f"📊 {result['summary'] or 'см. ниже'}\n\n"
                f"{result['stdout'][-800:]}"
            )
    else:
        # Нет тестов — обычный smoke-тест
        main_file = None
        for name in ["bot.py", "main.py"]:
            if name in files:
                main_file = name
                break
        if not main_file:
            bot.reply_to(message, "Нет ни test_*.py, ни bot.py/main.py — нечего тестировать.")
            return
        from sandbox import test_project_safe
        result = test_project_safe(files, main_file, timeout=15)
        if result["ok"]:
            out = result["stdout"].strip()[:500] or "(нет вывода)"
            bot.reply_to(message, f"✅ Smoke-тест #{pid} пройден\n\nФайл: {main_file}\n\n{out}")
        else:
            err = result.get("error") or result.get("stderr", "")[:500]
            bot.reply_to(message, f"❌ Тест #{pid} провален\n\nОшибка:\n{err}")


def _process_code_input(message, action):
    """Обработчик следующего сообщения — код для review/explain/fix."""
    code_text = message.text or ""
    if len(code_text) < 15:
        bot.reply_to(message, "Код слишком короткий. Попробуй ещё раз.")
        return

    headers = {
        "review": "🔍 Делаю ревью... 15-30 сек.",
        "explain": "📖 Объясняю... 15-30 сек.",
        "fix": "🔧 Разбираю ошибку... 15-30 сек.",
    }
    bot.reply_to(message, headers.get(action, "Обрабатываю..."))

    if action == "review":
        result = review_code(code_text)
    elif action == "explain":
        result = explain_code(code_text)
    elif action == "fix":
        result = fix_code(code_text)
    else:
        result = None

    if not result or "Ошибка ИИ" in result or "Лимит ИИ" in result:
        bot.reply_to(message, "⚠ Не получилось: " + str(result)[:200])
        return

    send_code(message, result)


@bot.message_handler(commands=['review'])
def handle_review(message):
    """/review — код-ревью. Можно /review <код> или /review + следующее сообщение."""
    code_text = message.text.replace("/review", "", 1).strip()
    if len(code_text) >= 15:
        bot.reply_to(message, "🔍 Делаю ревью... 15-30 сек.")
        result = review_code(code_text)
        if not result or "Ошибка ИИ" in result:
            bot.reply_to(message, "⚠ Не получилось: " + str(result)[:200])
            return
        send_code(message, result)
    else:
        bot.reply_to(message, "📝 Пришли код следующим сообщением.")
        bot.register_next_step_handler(message, lambda m: _process_code_input(m, "review"))


@bot.message_handler(commands=['explain'])
def handle_explain(message):
    """/explain — объяснение кода."""
    code_text = message.text.replace("/explain", "", 1).strip()
    if len(code_text) >= 15:
        bot.reply_to(message, "📖 Объясняю... 15-30 сек.")
        result = explain_code(code_text)
        if not result or "Ошибка ИИ" in result:
            bot.reply_to(message, "⚠ Не получилось: " + str(result)[:200])
            return
        send_code(message, result)
    else:
        bot.reply_to(message, "📝 Пришли код следующим сообщением.")
        bot.register_next_step_handler(message, lambda m: _process_code_input(m, "explain"))


@bot.message_handler(commands=['fix'])
def handle_fix(message):
    """/fix — починить код. Пришли код + traceback одним сообщением."""
    text = message.text.replace("/fix", "", 1).strip()
    if len(text) >= 15:
        bot.reply_to(message, "🔧 Разбираю ошибку... 15-30 сек.")
        result = fix_code(text)
        if not result or "Ошибка ИИ" in result:
            bot.reply_to(message, "⚠ Не получилось: " + str(result)[:200])
            return
        send_code(message, result)
    else:
        bot.reply_to(message,
            "📝 Пришли код И ошибку одним сообщением. Пример:" + chr(10) + chr(10) +
            "def f():" + chr(10) +
            "    return 1/0" + chr(10) + chr(10) +
            "ZeroDivisionError: division by zero"
        )
        bot.register_next_step_handler(message, lambda m: _process_code_input(m, "fix"))




# ============================================================
# ТЕСТЫ, АРХИТЕКТУРА, РЕФАКТОРИНГ, ВЫБОР МОДЕЛИ
# ============================================================

def _process_code_for(message, action):
    """Обработчик кода для /tests и /refactor."""
    code_text = message.text or ""
    if len(code_text) < 15:
        bot.reply_to(message, "Код слишком короткий.")
        return

    if action == "tests":
        bot.reply_to(message, "🧪 Генерирую тесты... 15-30 сек.")
        tests_code = generate_tests(code_text)
        if not tests_code or "Ошибка ИИ" in tests_code:
            bot.reply_to(message, "⚠ Не получилось: " + str(tests_code)[:200])
            return

        # Определяем имя модуля — Gemini пишет "from X import Y"
        import re as _re
        module_name = None
        # Ловим и "from x import", и "from x.y import", и "import x"
        m = _re.search(r"^from\s+(\w+)", tests_code, _re.MULTILINE)
        if not m:
            m = _re.search(r"^import\s+(\w+)", tests_code, _re.MULTILINE)
        if m:
            module_name = m.group(1)

        if module_name:
            bot.reply_to(message, "🧪 Запускаю тесты через pytest... 15-30 сек.")
            files = {
                module_name + ".py": code_text,
                "test_" + module_name + ".py": tests_code,
            }
            from sandbox import run_pytest
            result = run_pytest(files, timeout=30)

            if result["ok"]:
                bot.reply_to(message,
                    f"✅ Тесты пройдены!\n"
                    f"📊 {result['summary'] or 'все тесты успешны'}"
                )
            else:
                # Берём объединённый вывод — ошибка может быть в stderr
                full = result.get("full_output") or result.get("stdout", "") or result.get("stderr", "")
                # Обрезаем до 1500 символов, отсекаем мусор сверху
                tail = full[-1500:] if len(full) > 1500 else full
                send_code(message,
                    f"❌ Тесты упали.\n"
                    f"📊 {result['summary'] or 'см. вывод ниже'}\n\n"
                    f"Подробности:\n{tail}"
                )
        else:
            bot.reply_to(message,
                "ℹ️ Сгенерированы тесты, но не удалось определить модуль для запуска.\n"
                "Вот код:"
            )
            send_code(message, tests_code)

    elif action == "refactor":
        bot.reply_to(message, "🔧 Рефакторю... 20-40 сек.")
        result = refactor_code(code_text)
        if not result or "Ошибка ИИ" in result:
            bot.reply_to(message, "⚠ Не получилось: " + str(result)[:200])
            return
        send_code(message, result)
    else:
        result = None


def _process_architect(message):
    """Обработчик описания для /architect."""
    task_text = message.text or ""
    if len(task_text) < 15:
        bot.reply_to(message, "Опиши задачу подробнее.")
        return
    bot.reply_to(message, "🏗 Проектирую... 20-40 сек.")
    result = architect_project(task_text)
    if not result or "Ошибка ИИ" in result:
        bot.reply_to(message, "⚠ Не получилось: " + str(result)[:200])
        return
    send_code(message, result)


@bot.message_handler(commands=['architect'])
def handle_architect(message):
    """/architect — спроектировать архитектуру по описанию."""
    task_text = message.text.replace("/architect", "", 1).strip()
    if len(task_text) >= 15:
        bot.reply_to(message, "🏗 Проектирую... 20-40 сек.")
        result = architect_project(task_text)
        if not result or "Ошибка ИИ" in result:
            bot.reply_to(message, "⚠ Не получилось: " + str(result)[:200])
            return
        send_code(message, result)
    else:
        bot.reply_to(message, "📝 Пришли описание задачи следующим сообщением.")
        bot.register_next_step_handler(message, _process_architect)


@bot.message_handler(commands=['model'])
def handle_model(message):
    """/model — переключить модель или показать текущую."""
    arg = message.text.replace("/model", "", 1).strip().lower()

    if not arg:
        current = get_current_model()
        bot.reply_to(message,
            f"🧠 Текущая модель: <code>{current}</code>\n\n"
            "Варианты:\n"
            "/model lite — gemini-3.5-flash-lite (быстро)\n"
            "/model pro — gemini-2.5-pro (умнее)\n"
            "/model latest — gemini-flash-latest",
            parse_mode="HTML"
        )
        return

    mapping = {
        "lite": "gemini-3.5-flash-lite",
        "pro": "gemini-2.5-pro",
        "latest": "gemini-flash-latest",
    }

    if arg not in mapping:
        bot.reply_to(message, "Неизвестный вариант. Используй: lite / pro / latest")
        return

    new_model = set_model(mapping[arg])
    bot.reply_to(message, f"✅ Модель переключена на <code>{new_model}</code>", parse_mode="HTML")




# ============================================================
# RAG-ПАМЯТЬ ПО ПРОЕКТАМ
# ============================================================

@bot.message_handler(commands=['find_project'])
def handle_find_project(message):
    """/find_project <запрос> — найти похожие проекты по смыслу."""
    query = message.text.replace("/find_project", "", 1).strip()
    if len(query) < 3:
        bot.reply_to(message, "Формат: /find_project авторизация через токен")
        return

    bot.reply_to(message, "🔎 Ищу похожие проекты... 10-20 сек.")
    results = find_similar_projects(query, top_k=5, min_score=0.5)

    if not results:
        bot.reply_to(message, "Ничего похожего не нашлось.")
        return

    lines = ["🔎 Похожие проекты (по смыслу):" + chr(10)]
    for pid, ptype, score, preview in results:
        lines.append(f"#{pid} [{TYPE_NAMES.get(ptype, ptype)}] — релевантность {int(score*100)}%")
        lines.append(f"   {preview}...")
        lines.append(f"   Скачать: /download {pid}")
        lines.append("")
    bot.reply_to(message, chr(10).join(lines))


@bot.message_handler(commands=['similar'])
def handle_similar(message):
    """/similar <id> — найти похожие проекты."""
    try:
        pid = int(message.text.replace("/similar", "", 1).strip())
    except ValueError:
        bot.reply_to(message, "Формат: /similar 5")
        return

    user_id = message.from_user.id
    row = get_project(pid, user_id)
    if not row:
        bot.reply_to(message, f"Проект #{pid} не найден.")
        return

    ptype, tz, code = row
    bot.reply_to(message, "🔎 Ищу похожие... 10-20 сек.")
    results = find_similar_projects(tz + chr(10) + code[:800], top_k=5, min_score=0.5)

    # Убираем сам проект
    results = [r for r in results if r[0] != pid]

    if not results:
        bot.reply_to(message, "Похожих не нашлось.")
        return

    lines = [f"🔎 Похожие на #{pid}:" + chr(10)]
    for rpid, rptype, score, preview in results:
        lines.append(f"#{rpid} [{TYPE_NAMES.get(rptype, rptype)}] — {int(score*100)}%")
        lines.append(f"   {preview}...")
        lines.append("")
    bot.reply_to(message, chr(10).join(lines))


@bot.message_handler(commands=['reindex'])
def handle_reindex(message):
    """/reindex — пересчитать embeddings для всех проектов."""
    bot.reply_to(message, "⚙️ Индексирую проекты... 30-60 сек.")
    try:
        done = backfill_embeddings()
        bot.reply_to(message, f"✅ Проиндексировано проектов: {done}")
    except Exception as e:
        import traceback
        bot.reply_to(message, f"⚠ Ошибка: {traceback.format_exc()[-300:]}")




# ============================================================
# FRONTEND — лендинги и одностраничники
# ============================================================

@bot.message_handler(commands=['make_site'])
def handle_make_site(message):
    """/make_site <ТЗ> — одностраничник (один HTML)."""
    tz = message.text.replace("/make_site", "", 1).strip()
    if len(tz) < 10:
        bot.reply_to(message, "Опиши сайт. Пример: /make_site лендинг для кофейни")
        return

    bot.reply_to(message, "🌐 Генерирую сайт... 20-60 сек.")

    try:
        html = generate_single_page(tz)
        if not html:
            bot.reply_to(message, "⚠ Не удалось сгенерировать.")
            return

        user_id = message.from_user.id
        files = {"index.html": html}
        pid = save_full_project(user_id, tz, files)

        # Автоиндексация для RAG
        try:
            from rag import save_embedding
            save_embedding(pid, "frontend", tz + chr(10) + html[:1000])
        except Exception:
            pass

        file_bytes = io.BytesIO(html.encode("utf-8"))
        file_bytes.name = "index.html"
        bot.send_document(
            message.chat.id,
            file_bytes,
            visible_file_name="index.html",
            caption=f"✅ Сайт готов!\n🆔 Проект #{pid}\n\nСкачать: /dl_full {pid}"
        )
    except Exception as e:
        import traceback
        bot.reply_to(message, f"🔥 Ошибка: {traceback.format_exc()[-300:]}")


@bot.message_handler(commands=['make_landing'])
def handle_make_landing(message):
    """/make_landing <ТЗ> — многофайловый лендинг (HTML + CSS + JS)."""
    tz = message.text.replace("/make_landing", "", 1).strip()
    if len(tz) < 10:
        bot.reply_to(message, "Опиши лендинг. Пример: /make_landing сайт для онлайн-курса")
        return

    bot.reply_to(message, "🌐 Генерирую лендинг... 30-90 сек.")

    try:
        files = generate_full_landing(tz)
        if not files:
            bot.reply_to(message, "⚠ Не удалось сгенерировать.")
            return

        user_id = message.from_user.id
        pid = save_full_project(user_id, tz, files)

        # Автоиндексация
        try:
            from rag import save_embedding
            code_all = chr(10).join(files.values())[:1000]
            save_embedding(pid, "frontend", tz + chr(10) + code_all)
        except Exception:
            pass

        file_list = "\n".join(["  • " + n for n in sorted(files.keys())])
        zip_buf = _make_zip(files)
        bot.send_document(
            message.chat.id,
            zip_buf,
            visible_file_name=f"landing_{pid}.zip",
            caption=(f"✅ Лендинг готов!\n🆔 Проект #{pid}\n\n"
                     f"📁 Файлы:\n{file_list}\n\n"
                     f"Скачать: /dl_full {pid}")
        )
    except Exception as e:
        import traceback
        bot.reply_to(message, f"🔥 Ошибка: {traceback.format_exc()[-300:]}")




# ============================================================
# SELENIUM — парсеры JS-сайтов
# ============================================================

@bot.message_handler(commands=['make_js_parser'])
def handle_make_js_parser(message):
    """/make_js_parser <ТЗ> — парсер для JS-сайта (Selenium)."""
    tz = message.text.replace("/make_js_parser", "", 1).strip()
    if len(tz) < 15:
        bot.reply_to(message,
            "Опиши что парсить. Пример:" + chr(10) +
            "/make_js_parser спарси названия и цены с сайта book24.ru, категория Python"
        )
        return

    bot.reply_to(message, "🌐 Генерирую Selenium-парсер... 30-90 сек.")

    try:
        files = generate_js_parser(tz)
        if not files:
            bot.reply_to(message, "⚠ Не удалось сгенерировать.")
            return

        user_id = message.from_user.id
        pid = save_full_project(user_id, tz, files)

        try:
            from rag import save_embedding
            code_all = chr(10).join(files.values())[:1000]
            save_embedding(pid, "selenium", tz + chr(10) + code_all)
        except Exception:
            pass

        file_list = "\n".join(["  • " + n for n in sorted(files.keys())])
        zip_buf = _make_zip(files)
        bot.send_document(
            message.chat.id,
            zip_buf,
            visible_file_name=f"js_parser_{pid}.zip",
            caption=(f"✅ Selenium-парсер готов!\n🆔 Проект #{pid}\n\n"
                     f"📁 Файлы:\n{file_list}\n\n"
                     f"⚠ Запускается ЛОКАЛЬНО (не на Render):\n"
                     f"1. Распакуй ZIP\n"
                     f"2. pip install -r requirements.txt\n"
                     f"3. python parser.py\n\n"
                     f"Скачать: /dl_full {pid}")
        )
    except Exception as e:
        import traceback
        bot.reply_to(message, f"🔥 Ошибка: {traceback.format_exc()[-300:]}")




@bot.message_handler(commands=['tests'])
def handle_tests(message):
    """/tests — сгенерировать и запустить pytest-тесты."""
    code_text = message.text.replace("/tests", "", 1).strip()
    if len(code_text) >= 15:
        _process_code_for(message, "tests")
    else:
        bot.reply_to(message, "📝 Пришли код следующим сообщением.")
        bot.register_next_step_handler(message, lambda m: _process_code_for(m, "tests"))



# ============================================================
# ИНТЕГРАЦИИ С СЕРВИСАМИ
# ============================================================

@bot.message_handler(commands=['integrate'])
def handle_integrate(message):
    """/integrate <сервис> <ТЗ> — модуль интеграции с внешним сервисом."""
    text = message.text.replace("/integrate", "", 1).strip()

    if not text:
        # Показываем список сервисов
        lines = ["🔌 Доступные интеграции:\n"]
        for key, info in SERVICES.items():
            lines.append(f"/integrate {key} <ТЗ>")
            lines.append(f"   {info['name']} — {info['description']}")
            lines.append("")
        lines.append("Пример: /integrate stars бот для продажи курса, цена 100 Stars")
        bot.reply_to(message, chr(10).join(lines))
        return

    parts = text.split(maxsplit=1)
    service_key = parts[0].lower()

    if service_key not in SERVICES:
        bot.reply_to(message,
            f"❓ Неизвестный сервис: {service_key}\n\n"
            f"Доступные: {', '.join(SERVICES.keys())}"
        )
        return

    if len(parts) < 2 or len(parts[1]) < 10:
        bot.reply_to(message,
            f"Опиши что нужно. Пример:" + chr(10) +
            f"/integrate {service_key} бот для продажи доступа"
        )
        return

    tz = parts[1]
    info = SERVICES[service_key]
    bot.reply_to(message, f"🔌 Генерирую интеграцию с {info['name']}... 30-90 сек.")

    try:
        files = generate_integration(service_key, tz)
        if not files:
            bot.reply_to(message, "⚠ Не удалось сгенерировать.")
            return

        user_id = message.from_user.id
        pid = save_full_project(user_id, tz, files)

        try:
            from rag import save_embedding
            code_all = chr(10).join(files.values())[:1000]
            save_embedding(pid, "integration_" + service_key, tz + chr(10) + code_all)
        except Exception:
            pass

        file_list = "\n".join(["  • " + n for n in sorted(files.keys())])
        zip_buf = _make_zip(files)
        bot.send_document(
            message.chat.id,
            zip_buf,
            visible_file_name=f"{service_key}_{pid}.zip",
            caption=(f"✅ Интеграция с {info['name']} готова!\n🆔 Проект #{pid}\n\n"
                     f"📁 Файлы:\n{file_list}\n\n"
                     f"📖 Документация: {info['docs']}\n\n"
                     f"Скачать: /dl_full {pid}")
        )
    except Exception as e:
        import traceback
        bot.reply_to(message, f"🔥 Ошибка: {traceback.format_exc()[-300:]}")


# Ловушка для НЕИЗВЕСТНЫХ команд (всё, что начинается с /, но не сработало выше)
@bot.message_handler(func=lambda m: m.text and m.text.startswith('/'))
def unknown_command(message):
    """Отвечает на неизвестные команды подсказкой."""
    cmd = message.text.split()[0]
    bot.reply_to(message,
        f"❓ Команда {cmd} не найдена.\n\n"
        "Доступные команды:\n"
        "/code — сгенерировать код\n"
        "/run — сгенерировать + выполнить\n"
        "/make_bot — Telegram-бот\n"
        "/make_parser — парсер\n"
        "/make_full — ZIP-проект\n"
        "/edit — доработать проект\n"
        "/projects — список проектов\n"
        "/test — проверить в sandbox\n"
        "/deploy — деплой на Render\n"
        "/help — полный список"
    )


# Ловушка для обычных сообщений (не команды)
@bot.message_handler(func=lambda m: not m.text.startswith('/'))
def echo_all(message):
    """Подсказывает команды при обычных сообщениях."""
    bot.reply_to(message,
        "Используй команды:\n"
        "/code <ТЗ> — сгенерировать код\n"
        "/make_full <ТЗ> — ZIP-проект\n"
        "/help — все команды"
    )
