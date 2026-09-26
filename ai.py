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
    """Генерирует проект + валидирует синтаксис. Если сломан — просит Gemini исправить."""
    if project_type == "bot":
        header = (
            "Ты — senior Python-разработчик. Создай ПОЛНЫЙ Telegram-бот по ТЗ клиента.\n"
            "КРИТИЧНО:\n"
            "- Используй pyTelegramBotAPI (telebot).\n"
            "- Весь код в ОДНОМ файле.\n"
            "- Первый блок — многострочный docstring с инструкцией (pip install, токен, запуск).\n"
            "- ВСЕ print() должны быть СТРОГО валидными f-строками: f'текст {переменная}' "
            "с обязательной буквой f и кавычками. НИКОГДА не пиши русские слова внутри {фигурных скобок}.\n"
            "- Никаких markdown-обёрток.\n"
            "- Код ДОЛЖЕН запускаться без SyntaxError.\n"
        )
    elif project_type == "parser":
        header = (
            "Ты — senior Python-разработчик. Создай скрипт парсинга по ТЗ.\n"
            "КРИТИЧНО:\n"
            "- requests + BeautifulSoup.\n"
            "- Один файл. Docstring-инструкция в начале.\n"
            "- ВСЕ print() — валидные f-строки с буквой f.\n"
            "- Никаких markdown-обёрток. Код запускается без SyntaxError.\n"
        )
    else:
        header = (
            "Ты — senior Python-разработчик. Создай скрипт автоматизации по ТЗ.\n"
            "КРИТИЧНО:\n"
            "- Один файл. Docstring-инструкция в начале.\n"
            "- ВСЕ print() — валидные f-строки с буквой f. "
            "Русский текст ТОЛЬКО в обычных строках, НЕ в фигурных скобках.\n"
            "- Никаких markdown-обёрток. Код запускается без SyntaxError.\n"
        )

    prompt = f"{header}\n\nТЗ клиента:\n{tz}"
    code = ask_ai(prompt, model="gemini-3.5-flash-lite", max_retries=2)
    if not code or "Ошибка ИИ" in code or "Лимит ИИ" in code:
        return None

    import re
    code = re.sub(r"^```(?:python)?\s*", "", code)
    code = re.sub(r"\s*```$", "", code)
    code = code.strip()

    import ast
    for attempt in range(max_fix_attempts):
        try:
            ast.parse(code)
            return code
        except SyntaxError as e:
            print(f"⚠ SyntaxError на попытке {attempt+1}: {e}", flush=True)
            fix_prompt = (
                f"Твой предыдущий код содержит SyntaxError:\n{e}\n\n"
                f"Вот код:\n{code}\n\n"
                "Исправь ТОЛЬКО синтаксис. Верни полный рабочий код. "
                "ВСЕ print() должны быть валидными (f-строки с буквой f и кавычками). "
                "Никаких русских слов внутри фигурных скобок."
            )
            code = ask_ai(fix_prompt, model="gemini-3.5-flash-lite", max_retries=2)
            if not code or "Ошибка ИИ" in code:
                return None
            code = re.sub(r"^```(?:python)?\s*", "", code)
            code = re.sub(r"\s*```$", "", code)
            code = code.strip()

    return code


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
