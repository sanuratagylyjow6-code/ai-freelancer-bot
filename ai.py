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
    """Отправляет промпт в Gemini. Retry + fallback через -latest алиасы."""
    # Основная + 2 fallback (алиасы -latest НИКОГДА не устаревают)
    models_to_try = [
        model or AI_MODEL,           # gemini-3.5-flash-lite
        "gemini-flash-lite-latest",  # lite-алиас, всегда актуальный
        "gemini-flash-latest",       # универсальный алиас
    ]
    last_error = None

    for m in models_to_try:
        for attempt in range(1, max_retries + 1):
            try:
                response = ai_client.models.generate_content(
                    model=m,
                    contents=prompt
                )
                return response.text
            except Exception as e:
                err_str = str(e)
                last_error = e

                # Лимит исчерпан — нет смысла повторять
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    return "Лимит ИИ исчерпан на сегодня."

                # 503 — перегружен, ждём дольше
                if "503" in err_str or "UNAVAILABLE" in err_str:
                    wait = 4 * attempt
                    print("503 на " + m + ", пауза " + str(wait) + "с", flush=True)
                    time.sleep(wait)
                    continue

                # Другие ошибки (404 модель устарела) — сразу к следующей модели
                if "404" in err_str or "NOT_FOUND" in err_str:
                    print("Модель " + m + " недоступна, fallback", flush=True)
                    break

                if attempt < max_retries:
                    time.sleep(2)

    return "После всех попыток: " + str(last_error)[:150]


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
    import ast as _ast
    import time as _time

    format_instruction = (
        "Верни файлы в СТРОГО таком формате (без markdown):" + chr(10) +
        "=== FILE: filename.py ===" + chr(10) +
        "<содержимое файла>" + chr(10) +
        "=== FILE: another.py ===" + chr(10) +
        "<содержимое>" + chr(10) +
        "=== END PROJECT ===" + chr(10) +
        "ВАЖНО: сгенерируй ВСЕ файлы ОДНИМ ответом." + chr(10) + chr(10)
    )

    type_instructions = {
        "bot": (
            "Создай многофайловый Telegram-бот. Обязательные файлы:" + chr(10) +
            "- bot.py — Flask на PORT, GET / отдаёт OK, polling в потоке" + chr(10) +
            "- handlers.py — все @bot.message_handler" + chr(10) +
            "- database.py — работа с SQLite" + chr(10) +
            "- config.py — BOT_TOKEN и настройки" + chr(10) +
            "- requirements.txt — зависимости" + chr(10) +
            "- README.md — инструкция" + chr(10) +
            "- test_bot.py — pytest-тесты" + chr(10)
        ),
        "parser": (
            "Создай парсер (requests + BeautifulSoup). Файлы:" + chr(10) +
            "- main.py, parser.py, config.py, requirements.txt, README.md" + chr(10)
        ),
        "automate": (
            "Создай скрипт автоматизации. Файлы:" + chr(10) +
            "- main.py, logic.py, config.py, requirements.txt, README.md" + chr(10)
        ),
    }

    prompt = (
        "Ты — senior Python-разработчик. " + type_instructions[project_type] + chr(10) + chr(10) +
        "КРИТИЧНО: все print() — валидные f-строки. Без markdown. Без SyntaxError." + chr(10) + chr(10) +
        format_instruction + chr(10) +
        "=== ТЗ КЛИЕНТА ===" + chr(10) + tz
    )

    def _parse_files(response_text):
        """Простой парсер без regex."""
        files = {}
        if "=== FILE:" not in response_text:
            return files
        # Разбиваем по маркеру "=== FILE:"
        parts = response_text.split("=== FILE:")
        for part in parts[1:]:
            if "===" not in part:
                continue
            # Имя файла — до следующего ==="
            idx = part.find("===")
            name = part[:idx].strip()
            rest = part[idx + 3:]
            # Отрезаем конец по === END PROJECT
            if "=== END PROJECT" in rest:
                rest = rest[:rest.find("=== END PROJECT")]
            code = rest.strip()
            # Чистим markdown-обёртки
            if code.startswith("```"):
                lines = code.split(chr(10))
                lines = lines[1:]  # убираем ```python
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                code = chr(10).join(lines).strip()
            # Фильтр: пропускаем .txt дубликаты .py (Gemini иногда генерит config.txt вместо config.py)
            if name.endswith(".txt") and not name.endswith("requirements.txt"):
                base_py = name.replace(".txt", ".py")
                if base_py in files or ("config" in name.lower()):
                    continue
            if name and code:
                files[name] = code
        return files

    response = ask_ai(prompt, model="gemini-3.5-flash-lite", max_retries=2)
    if not response or "Ошибка ИИ" in response or "Лимит ИИ" in response:
        return None

    files = _parse_files(response)
    if not files:
        print("Парсинг не дал файлов. Ответ (первые 500): " + str(response)[:500], flush=True)
        return None

    # Валидация синтаксиса
    for attempt in range(max_fix_attempts):
        broken = None
        for name, code in files.items():
            if name.endswith(".py"):
                try:
                    _ast.parse(code)
                except SyntaxError as e:
                    broken = (name, code, e)
                    break
        if broken is None:
            break
        bad_name, bad_code, err = broken
        print("SyntaxError в " + bad_name + ": " + str(err), flush=True)
        fix_prompt = (
            "Файл " + bad_name + " содержит SyntaxError: " + str(err) + chr(10) + chr(10) +
            "Вот код:" + chr(10) + bad_code + chr(10) + chr(10) +
            "Исправь синтаксис. Верни весь проект в формате === FILE: name === ... === END PROJECT ==="
        )
        response = ask_ai(fix_prompt, model="gemini-3.5-flash-lite", max_retries=2)
        if not response or "Ошибка ИИ" in response:
            break
        new_files = _parse_files(response)
        if new_files:
            files = new_files

    # Retry при малом числе файлов
    if len(files) < 4:
        print("Мало файлов (" + str(len(files)) + "). Retry...", flush=True)
        print("Сырой ответ (500): " + str(response)[:500], flush=True)
        for retry_idx in range(2):
            _time.sleep(3)
            response = ask_ai(prompt, model="gemini-flash-latest", max_retries=2)
            if not response or "Ошибка ИИ" in response:
                continue
            new_files = _parse_files(response)
            if len(new_files) >= 4:
                print("Retry успешен, файлов: " + str(len(new_files)), flush=True)
                return new_files
        print("После retry всё ещё мало: " + str(len(files)), flush=True)

    return files

def classify_job(title, description):
    """Определяет категорию вакансии: Python / Bot / Parser / Automation / Other."""
    prompt = (
        "Определи категорию вакансии. Верни ОДНО слово из списка:\n"
        "Python — если про Python-разработку\n"
        "Bot — если про Telegram-ботов или чат-ботов\n"
        "Parser — если про парсинг, скрейпинг, сбор данных\n"
        "Automation — если про автоматизацию\n"
        "Other — если не подходит\n\n"
        "Название: " + title + "\n"
        "Описание: " + description[:400] + "\n\n"
        "Ответь ОДНИМ словом."
    )
    result = ask_ai(prompt, model="gemini-3.5-flash-lite", max_retries=1)
    if not result:
        return "Other"
    result = result.strip().strip(".,!?").strip()
    valid = ["Python", "Bot", "Parser", "Automation", "Other"]
    for v in valid:
        if v.lower() in result.lower():
            return v
    return "Other"


def generate_apply_draft(title, description, category):
    """Генерирует черновик письма клиенту по вакансии."""
    prompt = (
        "Ты — Python-разработчик-фрилансер. Напиши КОРОТКОЕ (до 120 слов) сообщение "
        "клиенту по вакансии. Стиль — уверенный, конкретный, без воды.\n\n"
        "Структура:\n"
        "1. Приветствие (1 строка)\n"
        "2. Понимание задачи (1 строка)\n"
        "3. Что могу сделать (2-3 пункта)\n"
        "4. Опыт с похожими проектами (1 строка)\n"
        "5. Вопрос или предложение\n\n"
        "Категория: " + (category or "разработка") + "\n"
        "Вакансия: " + title + "\n"
        "Описание: " + description[:500] + "\n\n"
        "Пиши от первого лица. Русский язык. Без markdown. Только текст письма."
    )
    return ask_ai(prompt, model="gemini-3.5-flash-lite", max_retries=2)


def evaluate_budget(title, description, category):
    """Оценивает адекватность бюджета. Возвращает (verdict, reason)."""
    prompt = (
        "Оцени бюджет вакансии для фрилансера-разработчика.\n\n"
        "Вакансия: " + title + "\n"
        "Описание: " + description[:500] + "\n\n"
        "Ответь СТРОГО одной строкой:\n"
        "BUDGET: <adequate|low|high|unclear> | REASON: <коротко до 80 символов>\n\n"
        "где:\n"
        "adequate — ставка адекватна рынку\n"
        "low — явно мало за эту работу\n"
        "high — щедро, стоит брать срочно\n"
        "unclear — бюджет не указан\n\n"
        "Без других слов."
    )
    result = ask_ai(prompt, model="gemini-3.5-flash-lite", max_retries=1)
    if not result:
        return ("unclear", "")
    import re
    m = re.search(r"BUDGET:\s*(\w+)", result)
    verdict = m.group(1).lower() if m else "unclear"
    rm = re.search(r"REASON:\s*(.+?)(?:$|\n)", result)
    reason = rm.group(1).strip()[:100] if rm else ""
    return (verdict, reason)


def generate_tz_questions(brief):
    """Генерирует 3-5 уточняющих вопросов по краткому ТЗ."""
    NL = chr(10)
    prompt = (
        "Ты — опытный project manager. Клиент дал краткое ТЗ:" + NL + NL +
        brief + NL + NL +
        "Задай РОВНО 3 вопроса, которые уточнят ТЗ для разработчика." + NL +
        "Вопросы должны касаться: функциональности, данных, стека." + NL +
        "Формат ответа — 3 строки, каждый вопрос начинается с номера:" + NL +
        "1. ..." + NL +
        "2. ..." + NL +
        "3. ..." + NL +
        "Без вступлений и комментариев."
    )
    return ask_ai(prompt, model="gemini-3.5-flash-lite", max_retries=2)


def compose_full_tz(brief, qa_pairs):
    """Собирает финальное ТЗ из краткого ТЗ + вопросов-ответов."""
    NL = chr(10)
    qa_text = ""
    for q, a in qa_pairs:
        qa_text += "Q: " + q + NL + "A: " + a + NL + NL

    prompt = (
        "Собери единое ТЗ для разработчика на основе:" + NL + NL +
        "ИСХОДНОЕ ТЗ: " + brief + NL + NL +
        "УТОЧНЕНИЯ:" + NL + qa_text + NL +
        "Верни структурированное ТЗ: цель, функции, данные, стек. Без воды, до 400 слов."
    )
    return ask_ai(prompt, model="gemini-3.5-flash-lite", max_retries=2)


def evaluate_job_complexity(title, description):
    """Оценивает сложность задачи. Гибкий парсинг + логирование."""
    prompt = (
        "Оцени время на выполнение задачи для опытного Python-разработчика." + chr(10) +
        "Задача: " + title + chr(10) +
        "Описание: " + description[:400] + chr(10) + chr(10) +
        "Ответь СТРОГО одной строкой:" + chr(10) +
        "TIME: <число> <единица>" + chr(10) +
        "Примеры: 'TIME: 30 минут', 'TIME: 2 часа', 'TIME: 3 дня', 'TIME: 2 недели'." + chr(10) +
        "Только одна строка, без пояснений."
    )
    result = ask_ai(prompt, model="gemini-3.5-flash-lite", max_retries=1)
    if not result:
        print("⏱ complexity: пустой ответ", flush=True)
        return None

    # Логируем сырой ответ (первые 200 символов) — для отладки
    print("⏱ complexity raw: " + str(result)[:200], flush=True)

    import re

    # Вариант 1: правильный формат "TIME: X"
    m = re.search(r"TIME:\s*(.+?)(?:$|\n)", result, re.IGNORECASE)
    if m:
        val = m.group(1).strip()[:30]
        if val:
            return val

    # Вариант 2: любое "число + единица времени" где-то в ответе
    m2 = re.search(
        r"(\d+[\.,]?\d*)\s*(минут|час|день|дней|дня|недел|недели|неделю|месяц|месяцев)",
        result, re.IGNORECASE
    )
    if m2:
        return m2.group(0).strip()[:30]

    # Вариант 3: ответ типа "~2 дня" или "около 5 часов"
    m3 = re.search(r"([~около\s]+\d+[^\n]{0,20})", result, re.IGNORECASE)
    if m3:
        return m3.group(1).strip()[:30]

    print("⏱ complexity: не распарсили ответ", flush=True)
    return None


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
