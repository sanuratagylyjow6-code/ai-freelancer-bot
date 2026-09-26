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
    """Оценивает релевантность вакансии через Gemini.
    Возвращает (score: int, reason: str) или (None, None) при ошибке."""
    prompt = f"""Ты оцениваешь вакансию для фрилансера.

Интересы фрилансера (ключевые слова): {keywords}

Вакансия:
Название: {title}
Описание: {description}

Оцени релевантность по шкале от 0 до 10:
- 10 — идеальное совпадение (в тексте прямо про эти темы)
- 7-9 — очень подходит
- 4-6 — частично подходит (упомянуто, но не главное)
- 1-3 — не подходит (другая сфера)
- 0 — совсем не про то

Ответь СТРОГО в формате (одна строка):
SCORE: X | REASON: короткое_объяснение_до_100_символов

Где X — число от 0 до 10. Без других слов и разметки."""

    response = ask_ai(prompt, max_retries=2)
    if not response or "Ошибка ИИ" in response:
        return None, None

    # Парсим ответ
    import re
    match = re.search(r"SCORE:\s*(\d+)", response)
    if not match:
        return None, None

    score = int(match.group(1))
    reason_match = re.search(r"REASON:\s*(.+?)(?:$|\n)", response)
    reason = reason_match.group(1).strip() if reason_match else ""

    return score, reason[:100]


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
