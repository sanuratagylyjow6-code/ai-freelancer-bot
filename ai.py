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


def generate_project(tz, project_type):
    """Генерирует полный проект по ТЗ. project_type: 'bot', 'parser', 'automate'."""
    if project_type == "bot":
        header = (
            "Ты — senior Python-разработчик. Создай ПОЛНЫЙ Telegram-бот по ТЗ клиента.\n"
            "Требования:\n"
            "- Используй библиотеку pyTelegramBotAPI (telebot).\n"
            "- Весь код в ОДНОМ файле.\n"
            "- В начале файла напиши многострочный комментарий-инструкцию: "
            "какие библиотеки установить (pip install ...), куда вставить BOT_TOKEN, как запустить.\n"
            "- Учти все детали ТЗ: команды, обработку ошибок, сохранение данных (SQLite).\n"
            "- Добавь короткие комментарии к ключевым местам.\n"
            "- Никаких markdown-обёрток, только чистый Python-код.\n"
        )
    elif project_type == "parser":
        header = (
            "Ты — senior Python-разработчик. Создай скрипт парсинга по ТЗ клиента.\n"
            "Требования:\n"
            "- Используй requests + BeautifulSoup.\n"
            "- Весь код в ОДНОМ файле.\n"
            "- В начале файла — многострочный комментарий-инструкция: "
            "что установить, что настроить, как запустить.\n"
            "- Результат сохраняй в CSV или JSON (в зависимости от ТЗ).\n"
            "- Обработай ошибки сети через try/except.\n"
            "- Никаких markdown-обёрток, только чистый Python-код.\n"
        )
    else:  # automate
        header = (
            "Ты — senior Python-разработчик. Создай скрипт автоматизации по ТЗ клиента.\n"
            "Требования:\n"
            "- Используй только стандартные библиотеки или openpyxl/pandas если нужно.\n"
            "- Весь код в ОДНОМ файле.\n"
            "- В начале файла — многострочный комментарий-инструкция.\n"
            "- Добавь понятные print() для отслеживания прогресса.\n"
            "- Обработай ошибки.\n"
            "- Никаких markdown-обёрток, только чистый Python-код.\n"
        )

    prompt = f"{header}\n\nТЗ клиента:\n{tz}"
    result = ask_ai(prompt, model="gemini-3.5-flash-lite", max_retries=2)
    if not result or "Ошибка ИИ" in result or "Лимит ИИ" in result:
        return None
    # Убираем markdown-обёртки, если Gemini их всё-таки добавил
    import re
    result = re.sub(r"^```(?:python)?\s*", "", result)
    result = re.sub(r"\s*```$", "", result)
    return result.strip()


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
