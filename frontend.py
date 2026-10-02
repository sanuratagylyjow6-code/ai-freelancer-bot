"""Генерация frontend-проектов: HTML/CSS/JS."""

import re


def _clean_markdown(text):
    """Убирает markdown-обёртки, если Gemini их добавил."""
    t = text or ""
    t = re.sub(r"^```(?:html|css|javascript|js)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _parse_files(response_text):
    """Парсит ответ Gemini в dict {filename: code}."""
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


def generate_single_page(tz):
    """Генерирует одностраничник: всё в одном index.html."""
    NL = chr(10)
    prompt = (
        "Ты — senior frontend-разработчик. Создай одностраничный сайт по ТЗ." + NL + NL +
        "КРИТИЧНО:" + NL +
        "- Всё в одном файле: HTML + CSS + JS внутри <style> и <script>" + NL +
        "- Семантический HTML (header, main, section, footer)" + NL +
        "- Адаптивная вёрстка (media queries) — работает на телефоне" + NL +
        "- Современный дизайн (flexbox/grid, приятные цвета, тени)" + NL +
        "- Без внешних библиотек, без CDN" + NL +
        "- Без markdown-обёрток. Только чистый HTML." + NL + NL +
        "ТЗ клиента:" + NL + tz[:2000]
    )
    from ai import ask_ai
    result = ask_ai(prompt, model="gemini-3.5-flash-lite", max_retries=2)
    if not result:
        return None
    return _clean_markdown(result)


def generate_full_landing(tz):
    """Генерирует многофайловый лендинг: index.html + style.css + script.js."""
    NL = chr(10)
    format_instruction = (
        "Верни файлы в СТРОГО таком формате:" + NL +
        "=== FILE: index.html ===" + NL +
        "<!DOCTYPE html>..." + NL +
        "=== FILE: style.css ===" + NL +
        "..." + NL +
        "=== FILE: script.js ===" + NL +
        "..." + NL +
        "=== FILE: README.md ===" + NL +
        "..." + NL +
        "=== END PROJECT ===" + NL + NL
    )

    prompt = (
        "Ты — senior frontend-разработчик. Создай полноценный лендинг по ТЗ." + NL + NL +
        "КРИТИЧНО:" + NL +
        "- Раздельные файлы: index.html, style.css, script.js, README.md" + NL +
        "- index.html подключает style.css через <link>, script.js через <script src>" + NL +
        "- Семантический HTML, адаптивная вёрстка" + NL +
        "- Современный дизайн, приятные цвета" + NL +
        "- README.md с инструкцией (как открыть, как задеплоить)" + NL +
        "- Без markdown-обёрток" + NL + NL +
        format_instruction + NL +
        "=== ТЗ КЛИЕНТА ===" + NL + tz[:2000]
    )

    from ai import ask_ai
    response = ask_ai(prompt, model="gemini-3.5-flash-lite", max_retries=2)
    if not response:
        return None

    files = _parse_files(response)
    return files if files else None
