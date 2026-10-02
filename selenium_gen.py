"""Генерация Selenium-парсеров для JS-сайтов."""

import re


def _clean_markdown(text):
    t = text or ""
    t = re.sub(r"^```(?:python)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _parse_files(response_text):
    files = {}
    if "=== FILE:" not in response_text:
        return files
    parts = response_text.split("=== FILE:")
    for part in parts[1:]:
        if "===" not in part:
            continue
        idx = part.find("===")
        name = part[:idx].strip()
        rest = part[idx + 3:]
        if "=== END PROJECT" in rest:
            rest = rest[:rest.find("=== END PROJECT")]
        code = _clean_markdown(rest)
        if name and code:
            files[name] = code
    return files


def generate_js_parser(tz):
    """Генерирует Selenium-парсер + README. Возвращает dict {filename: code}."""
    NL = chr(10)
    format_instruction = (
        "Верни файлы строго так:" + NL +
        "=== FILE: parser.py ===" + NL +
        "<код>" + NL +
        "=== FILE: requirements.txt ===" + NL +
        "selenium" + NL + "webdriver-manager" + NL + "beautifulsoup4" + NL +
        "=== FILE: README.md ===" + NL +
        "<инструкция>" + NL +
        "=== END PROJECT ===" + NL + NL
    )

    prompt = (
        "Ты — senior Python-разработчик, специалист по парсингу JS-сайтов." + NL + NL +
        "Создай Selenium-скрипт парсинга по ТЗ клиента." + NL + NL +
        "ТРЕБОВАНИЯ:" + NL +
        "- Используй selenium + webdriver-manager (не требует ручной установки Chrome)" + NL +
        "- Функция get_driver() с опциями: --headless, --no-sandbox, --disable-dev-shm-usage" + NL +
        "- Явные ожидания WebDriverWait (не time.sleep где можно)" + NL +
        "- Парсинг через BeautifulSoup после загрузки" + NL +
        "- Сохранение в CSV (utf-8-sig — важно для Excel)" + NL +
        "- try/except для ошибок сети и элементов" + NL +
        "- print() прогресса" + NL +
        "- Не используй input()" + NL + NL +
        "README.md должен содержать:" + NL +
        "1. Установка: pip install -r requirements.txt" + NL +
        "2. Запуск: python parser.py" + NL +
        "3. Что делает скрипт" + NL +
        "4. Где взять данные (файл CSV)" + NL + NL +
        format_instruction + NL +
        "=== ТЗ КЛИЕНТА ===" + NL + tz[:2000]
    )

    from ai import ask_ai
    response = ask_ai(prompt, model="gemini-3.5-flash-lite", max_retries=2)
    if not response:
        return None
    files = _parse_files(response)
    return files if files else None
