# handlers.py — все команды бота
# 9 команд: /start /help /model /make /preview /edit /myprojects
#           /dl /test /critique + загрузка файлов (PDF/TXT)

import io
import os
import json
import zipfile
import html

from core import bot
from config import TELEGRAM_MAX_LEN, OWNER_ID
from database import (
    save_user, get_user_stats, save_full_project,
    get_user_full_projects, get_full_project, update_full_project,
    save_user_file, get_latest_user_file, clear_user_files
)
from ai import (
    generate_full_project, edit_project, run_code, auto_fix,
    set_model, get_current_model
)
from sandbox import test_project_safe, quick_smoke_test
from file_parser import extract_text

def split_long_message(text, max_len=None):
    # Режет длинный текст на куски для Telegram
    limit = max_len or TELEGRAM_MAX_LEN
    return [text[i:i+limit] for i in range(0, len(text), limit)]

def send_code(message, code_text):
    # Отправляет код в чат, оборачивая в тройные бэктики
    wrapped = f'```python\n{code_text}\n```'
    for chunk in split_long_message(wrapped):
        bot.send_message(message.chat.id, chunk)

def _make_zip(files_dict):
    # Собирает ZIP из dict {имя: содержимое}, возвращает байты
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, content in files_dict.items():
            zf.writestr(name, content)
    buf.seek(0)
    return buf.read()

def _detect_main_file(files_dict):
    # Определяет главный файл для запуска тестов
    priority = ['main.py', 'app.py', 'bot.py', 'run.py']
    for name in priority:
        if name in files_dict:
            return name
    for name in files_dict:
        if name.endswith('.py'):
            return name
    return None

# ── ГЛАВНЫЙ ЗАМОК: только OWNER_ID имеет доступ ─────────────────────────
@bot.message_handler(                                                        # декоратор
    func=lambda m: m.from_user is not None and m.from_user.id != OWNER_ID,    # фильтр: чужой
    content_types=['text', 'document', 'photo', 'video', 'audio', 'voice', 'sticker']  # любые медиа
)
def handle_blocked(message):                                                  # обработчик
    # Отсекает всех, кроме владельца. Первый в цепочке — перехватывает раньше других.
    try:                                                                      # защита от сбоев
        bot.send_message(message.chat.id, '⛔ Доступ закрыт.')                 # ответ
    except Exception:                                                          # если не смог
        pass                                                                   # молча выходим
    return                                                                    # стоп


@bot.message_handler(commands=['start'])
def handle_start(message):
    # Регистрирует юзера и приветствует
    user_id = message.from_user.id
    username = message.from_user.username or 'без_имени'
    if user_id != OWNER_ID:
        bot.send_message(message.chat.id, '⛔ Доступ закрыт.')
        return
    save_user(user_id, username)
    text = (
        '👋 Привет! Я — Python-фабрика.\n\n'
        'Даёшь ТЗ → получаешь готовый проект в ZIP.\n\n'
        'Команды: /help'
    )
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['help'])
def handle_help(message):
    # Показывает список команд
    text = (
        "🤖 Python-фабрика\n\n"
        "ГЕНЕРАЦИЯ:\n"
        "/make <ТЗ> — создать проект\n"
        "/preview <ТЗ> — структура до генерации\n"
        "/edit <id> <правки> — доработать\n\n"
        "ПРОЕКТЫ:\n"
        "/myprojects — список моих проектов\n"
        "/dl <id> — скачать ZIP\n"
        "/test <id> — запустить тесты\n"
        "/critique <id> — QA-проверка проекта\n\n"
        "НАСТРОЙКИ:\n"
        "/model — показать текущую модель\n"
        "/model lite — быстрая\n"
        "/model pro — умная\n"
        "/model latest — свежая\n\n"
        "ФАЙЛЫ:\n"
        "Отправь PDF/TXT/MD — станет ТЗ\n"
        "/myfile — последний файл\n"
        "/clearfile — удалить файлы"
    )
    bot.send_message(message.chat.id, text)  # без Markdown

@bot.message_handler(commands=['model'])
def handle_model(message):
    # Показывает/меняет модель Gemini
    parts = message.text.split(maxsplit=1)
    if len(parts) == 1:
        current = get_current_model()
        bot.send_message(message.chat.id, f'🎯 Текущая модель: `{current}`')
        return
    alias = parts[1].strip().lower()
    mapping = {
        'lite': 'gemini-3.5-flash-lite',
        'pro': 'gemini-2.5-pro',
        'latest': 'gemini-flash-latest'
    }
    if alias not in mapping:
        bot.send_message(message.chat.id, '❓ Используй: lite / pro / latest')
        return
    set_model(mapping[alias])
    bot.send_message(message.chat.id, f'✅ Модель: `{mapping[alias]}`')

@bot.message_handler(content_types=['document'])
def handle_document(message):
    # Принимает PDF/TXT/MD и сохраняет как ТЗ
    doc = message.document
    try:
        file_info = bot.get_file(doc.file_id)
        downloaded = bot.download_file(file_info.file_path)
        text = extract_text(downloaded, doc.file_name)
        if not text.strip():
            bot.send_message(message.chat.id, '⚠️ Не удалось извлечь текст.')
            return
        save_user_file(message.from_user.id, doc.file_name, text)
        preview = text[:300] + ('...' if len(text) > 300 else '')
        bot.send_message(message.chat.id, f'📄 Файл *{doc.file_name}* сохранён как ТЗ.\n\n{preview}')
    except Exception as e:
        bot.send_message(message.chat.id, f'❌ Ошибка: {e}')

@bot.message_handler(commands=['myfile'])
def handle_myfile(message):
    # Показывает последний загруженный файл
    row = get_latest_user_file(message.from_user.id)
    if not row:
        bot.send_message(message.chat.id, '📭 Файлов нет.')
        return
    filename, content = row
    preview = content[:500] + ('...' if len(content) > 500 else '')
    bot.send_message(message.chat.id, f'📄 *{filename}*\n\n{preview}')

@bot.message_handler(commands=['clearfile'])
def handle_clearfile(message):
    # Удаляет все загруженные файлы юзера
    clear_user_files(message.from_user.id)
    bot.send_message(message.chat.id, '🗑 Все файлы удалены.')
def _get_tz(message):
    # Достаёт ТЗ: либо из текста команды, либо из загруженного файла
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1 and parts[1].strip():
        return parts[1].strip()
    row = get_latest_user_file(message.from_user.id)
    if row:
        return row[1]
    return None

@bot.message_handler(commands=['make'])
def handle_make(message):
    # ⭐ Создаёт проект по ТЗ, сохраняет в БД, отдаёт ZIP
    tz = _get_tz(message)
    if not tz:
        bot.send_message(message.chat.id, '📝 Напиши ТЗ: /make бот для ...\nИли загрузи PDF/TXT.')
        return
    bot.send_message(message.chat.id, '⏳ Генерирую проект + QA-проверка... (2-4 минуты)')
    try:
        result = generate_full_project(tz)
        files = result.get('files', {})
        ptype = result.get('type', 'unknown')
        if not files:
            bot.send_message(message.chat.id, '❌ Gemini вернул пустой результат. Попробуй переформулировать ТЗ.')
            return
        files_json = json.dumps(files, ensure_ascii=False)
        pid = save_full_project(message.from_user.id, tz, files_json)
        file_list = '\n'.join('• ' + name for name in files)
        text = '✅ Проект #' + str(pid) + ' создан!\n\nТип: *' + ptype + '*\nФайлы:\n' + file_list + '\n\nСкачать: /dl ' + str(pid)
        bot.send_message(message.chat.id, text)  # без Markdown
    except Exception as e:
        bot.send_message(message.chat.id, f'❌ Ошибка: {e}')

@bot.message_handler(commands=['preview'])
def handle_preview(message):
    # Показывает план проекта ДО генерации кода
    tz = _get_tz(message)
    if not tz:
        bot.send_message(message.chat.id, '📝 Напиши ТЗ: /preview ...')
        return
    bot.send_message(message.chat.id, '🔍 Анализирую ТЗ...')
    try:
        from ai import ask_ai
        prompt = 'Проанализируй ТЗ. Верни КРАТКО (без кода):\n'
        prompt += '1. Тип проекта (bot/parser/api/website/...).\n'
        prompt += '2. Список файлов с описанием каждого (5-10 строк).\n'
        prompt += '3. Основные библиотеки.\n\n'
        prompt += 'ТЗ: ' + tz
        answer = ask_ai(prompt)
        for chunk in split_long_message(answer):
            bot.send_message(message.chat.id, chunk)
    except Exception as e:
        bot.send_message(message.chat.id, f'❌ Ошибка: {e}')

@bot.message_handler(commands=['edit'])
def handle_edit(message):
    # Вносит правки в проект, версионирует, отдаёт обновлённый ZIP
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.send_message(message.chat.id, '📝 Формат: /edit <id> <что поменять>')
        return
    try:
        pid = int(parts[1])
    except ValueError:
        bot.send_message(message.chat.id, '❌ id должен быть числом.')
        return
    tz_edit = parts[2].strip()
    row = get_full_project(pid, message.from_user.id)
    if not row:
        bot.send_message(message.chat.id, f'❌ Проект #{pid} не найден.')
        return
    _, tz_orig, files_json = row
    files = json.loads(files_json)
    bot.send_message(message.chat.id, '✏️ Дорабатываю...')
    try:
        updated = edit_project(files, tz_edit)
        if not updated:
            bot.send_message(message.chat.id, '❌ Gemini не вернул файлы.')
            return
        files.update(updated)
        new_json = json.dumps(files, ensure_ascii=False)
        update_full_project(pid, message.from_user.id, new_json)
        changed = ', '.join(updated.keys())
        bot.send_message(message.chat.id, f'✅ Проект #{pid} обновлён.\nИзменено: {changed}')
    except Exception as e:
        bot.send_message(message.chat.id, f'❌ Ошибка: {e}')
@bot.message_handler(commands=['myprojects'])
def handle_myprojects(message):
    # Показывает список проектов юзера
    rows = get_user_full_projects(message.from_user.id, limit=15)
    if not rows:
        bot.send_message(message.chat.id, '📭 Проектов нет. Начни с /make')
        return
    text = '📦 *Мои проекты:*\n\n'
    for pid, tz, created in rows:
        short = tz[:60] + ('...' if len(tz) > 60 else '')
        text += f'*#{pid}* — {short}\n'
    bot.send_message(message.chat.id, text)  # без Markdown

@bot.message_handler(commands=['dl'])
def handle_dl(message):
    # Отдаёт ZIP с проектом
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.send_message(message.chat.id, '📝 Формат: /dl <id>')
        return
    try:
        pid = int(parts[1])
    except ValueError:
        bot.send_message(message.chat.id, '❌ id — число.')
        return
    row = get_full_project(pid, message.from_user.id)
    if not row:
        bot.send_message(message.chat.id, f'❌ Проект #{pid} не найден.')
        return
    _, _, files_json = row
    files = json.loads(files_json)
    try:
        zip_bytes = _make_zip(files)
        filename = f'project_{pid}.zip'
        bot.send_document(message.chat.id, io.BytesIO(zip_bytes), visible_file_name=filename)
    except Exception as e:
        bot.send_message(message.chat.id, f'❌ Ошибка: {e}')

@bot.message_handler(commands=['test'])
def handle_test(message):
    # Запускает smoke-тест проекта в изолированной папке
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.send_message(message.chat.id, '📝 Формат: /test <id>')
        return
    try:
        pid = int(parts[1])
    except ValueError:
        bot.send_message(message.chat.id, '❌ id — число.')
        return
    row = get_full_project(pid, message.from_user.id)
    if not row:
        bot.send_message(message.chat.id, f'❌ Проект #{pid} не найден.')
        return
    _, _, files_json = row
    files = json.loads(files_json)
    main_file = _detect_main_file(files)
    if not main_file:
        bot.send_message(message.chat.id, '⚠️ В проекте нет .py файлов.')
        return
    bot.send_message(message.chat.id, f'🧪 Тестирую {main_file}...')
    try:
        result = test_project_safe(files, main_file, timeout=120)
        ok = result.get('ok', False)
        stdout = result.get('stdout', '')[:1500]
        stderr = result.get('stderr', '')[:1500]
        err = result.get('error') or ''
        emoji = '✅' if ok else '❌'
        text = f'{emoji} Тест завершён.\n'
        if err:
            text += f'\nERROR: {err}\n'
        text += f'\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}'
        for chunk in split_long_message(text):
            bot.send_message(message.chat.id, chunk)                # отправка
    except Exception as e:
        bot.send_message(message.chat.id, f'❌ Ошибка теста: {e}')

@bot.message_handler(func=lambda m: m.text and m.text.startswith('/'))
def handle_unknown(message):
    # Подсказывает на неизвестные команды
    bot.send_message(message.chat.id, '❓ Неизвестная команда. Список: /help')

@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_echo(message):
    # Подсказывает, если написали не команду
    bot.send_message(message.chat.id, '💡 Напиши /make <ТЗ> — создам проект. Помощь: /help')