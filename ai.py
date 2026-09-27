"""Работа с Gemini."""

import os
import time
import traceback
from google import genai
from config import AI_MODEL, MAX_ATTEMPTS


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY не задан в переменных окружения")

ai_client = genai.Client(api_key=GEMINI_API_KEY)


def ask_ai(prompt, model=None, max_retries=3):
    model = model or AI_MODEL
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            response = ai_client.models.generate_content(
                model=model,
                contents=prompt
            )
            return response.text
        except Exception as e:
            last_error = e
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                return "⚠ Лимит ИИ на сегодня исчерпан."
            if attempt < max_retries:
                time.sleep(3)
    return f"⚠ После {max_retries} попыток: {last_error}"


def evaluate_job_relevance(title, description, keywords):
    """Оценивает релевантность через Gemini. Возвращает (score, reason) или (None, None)."""
    prompt = f"""Ты оцениваешь вакансию для фрилансера.

Интересы: {keywords}

Вакансия:
Название: {title}
Описание: {description}

Оцени релевантность от 0 до 10:
- 10 — идеальное совпадение
- 7-9 — очень подходит
- 4-6 — частично
- 1-3 — не подходит
- 0 — совсем не то

Ответь СТРОГО одной строкой:
SCORE: X | REASON: короткое_объяснение

Без markdown, без других слов."""

    # Модель с большим лимитом
    response = ask_ai(prompt, model="gemini-3.5-flash-lite", max_retries=2)
    if not response or "Ошибка ИИ" in response or "Лимит ИИ" in response:
        return None, None

    import re
    match = re.search(r"SCORE:\s*(\d+)", response)
    if not match:
        return None, None
    score = int(match.group(1))
    reason_match = re.search(r"REASON:\s*(.+?)(?:$|\n)", response)
    reason = reason_match.group(1).strip() if reason_match else ""
    return score, reason[:100]


def generate_project(tz, project_type, max_fix_attempts=2):
    """Генерирует проект + валидирует синтаксис."""
    headers = {
        "bot": "Ты — senior Python-разработчик. Создай ПОЛНЫЙ Telegram-бот по ТЗ.\nКРИТИЧНО: один файл, docstring-инструкция в начале, все print() — валидные f-строки с буквой f и кавычками. Без markdown. Без SyntaxError.",
        "parser": "Ты — senior Python-разработчик. Создай скрипт парсинга (requests + BeautifulSoup). Один файл, docstring-инструкция, все print() — валидные f-строки. Без SyntaxError.",
        "automate": "Ты — senior Python-разработчик. Создай скрипт автоматизации. Один файл, docstring-инструкция, все print() — валидные f-строки. Русский текст ТОЛЬКО в обычных строках, не в фигурных скобках. Без SyntaxError.",
    }
    header = headers.get(project_type, headers["automate"])
    prompt = header + "\n\nТЗ клиента:\n" + tz

    code = ask_ai(prompt, model="gemini-3.5-flash-lite", max_retries=2)
    if not code or "Ошибка ИИ" in code or "Лимит ИИ" in code:
        return None

    import re, ast
    code = re.sub(r"^```(?:python)?\s*", "", code)
    code = re.sub(r"\s*```$", "", code)
    code = code.strip()

    for attempt in range(max_fix_attempts):
        try:
            ast.parse(code)
            return code
        except SyntaxError as e:
            print("SyntaxError попытка " + str(attempt+1) + ": " + str(e), flush=True)
            fix_prompt = "Код содержит SyntaxError: " + str(e) + "\n\nВот код:\n" + code + "\n\nИсправь ТОЛЬКО синтаксис. Верни полный рабочий код."
            code = ask_ai(fix_prompt, model="gemini-3.5-flash-lite", max_retries=2)
            if not code or "Ошибка ИИ" in code:
                return None
            code = re.sub(r"^```(?:python)?\s*", "", code)
            code = re.sub(r"\s*```$", "", code)
            code = code.strip()
    return code


def edit_project(existing_code, tz_edit, project_type, max_fix_attempts=2):
    """Дорабатывает существующий проект по правкам клиента."""
    prompt = (
        "Ты — senior Python-разработчик. Тебе дан РАБОЧИЙ код проекта.\n"
        "Клиент просит внести правки. Верни ПОЛНЫЙ обновлённый код.\n\n"
        "КРИТИЧНО:\n"
        "- Не ломай существующую функциональность.\n"
        "- Вноси ТОЛЬКО запрошенные правки.\n"
        "- Один файл. Docstring-инструкция в начале.\n"
        "- Все print() — валидные f-строки.\n"
        "- Без markdown-обёрток. Без SyntaxError.\n\n"
        "=== ТЕКУЩИЙ КОД ===\n" + existing_code + "\n=== КОНЕЦ ===\n\n"
        "=== ПРАВКИ КЛИЕНТА ===\n" + tz_edit
    )

    code = ask_ai(prompt, model="gemini-3.5-flash-lite", max_retries=2)
    if not code or "Ошибка ИИ" in code or "Лимит ИИ" in code:
        return None

    import re, ast
    code = re.sub(r"^```(?:python)?\s*", "", code)
    code = re.sub(r"\s*```$", "", code)
    code = code.strip()

    for attempt in range(max_fix_attempts):
        try:
            ast.parse(code)
            return code
        except SyntaxError as e:
            print("SyntaxError: " + str(e), flush=True)
            fix_prompt = "Код с SyntaxError: " + str(e) + "\n\n" + code + "\n\nИсправь синтаксис."
            code = ask_ai(fix_prompt, model="gemini-3.5-flash-lite", max_retries=2)
            if not code or "Ошибка ИИ" in code:
                return None
            code = re.sub(r"^```(?:python)?\s*", "", code)
            code = re.sub(r"\s*```$", "", code)
            code = code.strip()
    return code



def generate_full_project(tz, project_type="bot", max_fix_attempts=2):
    """Генерирует многофайловый проект. Возвращает dict {filename: code} или None."""

    # Формат ответа — разделители между файлами
    format_instruction = (
        "Верни файлы в СТРОГО таком формате (без markdown):\n"
        "=== FILE: filename.py ===\n"
        "<содержимое файла>\n"
        "=== FILE: another.py ===\n"
        "<содержимое>\n"
        "=== END PROJECT ===\n\n"
    )

    type_instructions = {
        "bot": (
            "Создай многофайловый Telegram-бот. Обязательные файлы:\n"
            "- bot.py — точка входа. ОБЯЗАТЕЛЬНО: поднимает простой HTTP-сервер на Flask, который отвечает на GET / текстом 'OK', и слушает порт из переменной окружения PORT (через app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))). Polling бота запускается В ОТДЕЛЬНОМ потоке через threading.Thread. Это нужно, чтобы Render видел открытый порт.\n"
            "- handlers.py — все @bot.message_handler\n"
            "- database.py — работа с SQLite\n"
            "- config.py — BOT_TOKEN и настройки\n"
            "- requirements.txt — зависимости (pip install -r)\n"
            "- README.md — краткая инструкция запуска\n"
            "Используй pyTelegramBotAPI."
        ),
        "parser": (
            "Создай многофайловый парсер. Обязательные файлы:\n"
            "- main.py — точка входа\n"
            "- parser.py — логика парсинга (requests + BeautifulSoup)\n"
            "- config.py — настройки (URL, селекторы)\n"
            "- requirements.txt\n"
            "- README.md\n"
        ),
        "automate": (
            "Создай многофайловый скрипт автоматизации. Обязательные файлы:\n"
            "- main.py — точка входа\n"
            "- logic.py — бизнес-логика\n"
            "- config.py — настройки\n"
            "- requirements.txt\n"
            "- README.md\n"
        ),
    }

    prompt = (
        "Ты — senior Python-разработчик. " + type_instructions[project_type] + "\n\n"
        "КРИТИЧНО:\n"
        "- Все .py файлы — валидные f-строки в print() с буквой f и кавычками.\n"
        "- Все import'ы между своими файлами должны работать (from config import ...).\n"
        "- Без markdown-обёрток. Без SyntaxError.\n"
        "- " + format_instruction + "\n"
        "=== ТЗ КЛИЕНТА ===\n" + tz
    )

    response = ask_ai(prompt, model="gemini-3.5-flash-lite", max_retries=2)
    if not response or "Ошибка ИИ" in response or "Лимит ИИ" in response:
        return None

    # Парсим ответ на файлы
    import re
    files = {}
    pattern = r"=== FILE:\s*(.+?)\s*===\s*\n(.*?)(?==== FILE:|=== END PROJECT|$)"
    for match in re.finditer(pattern, response, re.DOTALL):
        name = match.group(1).strip()
        code = match.group(2).strip()
        if name and code:
            files[name] = code

    if not files:
        return None

    # Валидируем .py файлы
    import ast
    for attempt in range(max_fix_attempts):
        broken = None
        for name, code in files.items():
            if name.endswith(".py"):
                try:
                    ast.parse(code)
                except SyntaxError as e:
                    broken = (name, code, e)
                    break
        if broken is None:
            return files  # всё ок

        bad_name, bad_code, err = broken
        print("SyntaxError в " + bad_name + ": " + str(err), flush=True)
        fix_prompt = (
            "Файл " + bad_name + " содержит SyntaxError: " + str(err) + "\n\n"
            "Вот его содержимое:\n" + bad_code + "\n\n"
            "Исправь ТОЛЬКО синтаксис. Верни весь проект заново в том же формате "
            "(=== FILE: имя === ... === END PROJECT ===)."
        )
        response = ask_ai(fix_prompt, model="gemini-3.5-flash-lite", max_retries=2)
        if not response or "Ошибка ИИ" in response:
            return files  # вернём как есть
        files = {}
        for match in re.finditer(pattern, response, re.DOTALL):
            name = match.group(1).strip()
            code = match.group(2).strip()
            if name and code:
                files[name] = code

    return files


def run_code(code_text):
    namespace = {}
    try:
        exec(code_text, namespace)
        return (True, "OK", namespace)
    except Exception:
        return (False, traceback.format_exc(), namespace)


def auto_fix(original_code, error_text):
    fix_prompt = (
        "Твой предыдущий код упал. Вот код:\n"
        f"```\n{original_code}\n```\n\n"
        f"Ошибка:\n```\n{error_text}\n```\n\n"
        "Исправь. Верни ТОЛЬКО код, без markdown."
    )
    return ask_ai(fix_prompt)
