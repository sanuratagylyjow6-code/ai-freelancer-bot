"""Генератор кода интеграций с внешними сервисами."""

import re


SERVICES = {
    "stars": {
        "name": "Telegram Stars",
        "description": "Оплата внутри Telegram (без платёжек, комиссия 30%)",
        "docs": "https://core.telegram.org/bots/payments-stars",
        "deps": ["pyTelegramBotAPI"],
        "extra_prompt": (
            "Используй Telegram Stars через bot.send_invoice с currency='XTR'. "
            "Обязательно обработай pre_checkout_query (ответить bot.answer_pre_checkout_query) "
            "и successful_payment (в message.successful_payment). "
            "Не забудь про provider_token — для Stars он пустой."
        ),
    },
    "yookassa": {
        "name": "ЮKassa",
        "description": "Приём карт в России",
        "docs": "https://yookassa.ru/developers/api",
        "deps": ["yookassa", "requests"],
        "extra_prompt": (
            "Используй библиотеку yookassa. "
            "Создавай платёж через Payment.create с confirmation redirect или embedded. "
            "Webhook для уведомлений: flask endpoint, возвращает 200. "
            "Проверяй статус платежа через Payment.find_one."
        ),
    },
    "stripe": {
        "name": "Stripe",
        "description": "Приём карт по всему миру",
        "docs": "https://stripe.com/docs/api",
        "deps": ["stripe"],
        "extra_prompt": (
            "Используй библиотеку stripe. "
            "Создавай Checkout Session через stripe.checkout.Session.create. "
            "Клиенту отдавай session.url. "
            "Webhook для события checkout.session.completed через flask."
        ),
    },
    "amocrm": {
        "name": "amoCRM",
        "description": "Отправка заявок в amoCRM",
        "docs": "https://www.amocrm.ru/developers/content/crm_platform/api-reference",
        "deps": ["requests"],
        "extra_prompt": (
            "Используй REST API amoCRM через requests. "
            "Авторизация по долгосрочному токену. "
            "Метод create_lead(name, phone, email) — создаёт сделку и контакт. "
            "Все HTTP-запросы с timeout и обработкой ошибок."
        ),
    },
    "gsheets": {
        "name": "Google Sheets",
        "description": "Логирование в Google-таблицу",
        "docs": "https://developers.google.com/sheets/api",
        "deps": ["gspread", "google-auth"],
        "extra_prompt": (
            "Используй gspread + Service Account. "
            "Путь к JSON-ключу — из переменной GOOGLE_CREDENTIALS_FILE. "
            "Методы: append_row(sheet_name, row_data), get_all(sheet_name). "
            "Клиент получает доступ через share таблицы на email сервисного аккаунта."
        ),
    },
    "openai": {
        "name": "OpenAI",
        "description": "ChatGPT в боте",
        "docs": "https://platform.openai.com/docs/api-reference",
        "deps": ["openai"],
        "extra_prompt": (
            "Используй библиотеку openai (v1+). "
            "Клиент OpenAI(api_key=...). "
            "Метод ask(prompt, system='...', model='gpt-4o-mini') — возвращает текст. "
            "Обрабатывай RateLimitError и APIError."
        ),
    },
}


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


def generate_integration(service_key, tz):
    """Генерирует модуль интеграции. Возвращает dict {filename: code}."""
    if service_key not in SERVICES:
        return None

    NL = chr(10)
    info = SERVICES[service_key]

    deps_str = ", ".join(info["deps"])

    format_instruction = (
        "Верни файлы в СТРОГО таком формате:" + NL +
        "=== FILE: integration.py ===" + NL +
        "<класс или функции интеграции>" + NL +
        "=== FILE: requirements.txt ===" + NL +
        "<зависимости, одна на строку>" + NL +
        "=== FILE: README.md ===" + NL +
        "<инструкция>" + NL +
        "=== FILE: example_usage.py ===" + NL +
        "<пример использования>" + NL +
        "=== END PROJECT ===" + NL + NL
    )

    prompt = (
        "Ты — senior Python-разработчик. Сгенерируй модуль интеграции с сервисом " + info["name"] + "." + NL + NL +
        "СПЕЦИФИКА СЕРВИСА:" + NL + info["extra_prompt"] + NL + NL +
        "ЗАВИСИМОСТИ (обязательно в requirements.txt): " + deps_str + NL + NL +
        "ТРЕБОВАНИЯ:" + NL +
        "- Код читаемый, с type hints" + NL +
        "- Все ключи/токены — из os.environ (никогда не хардкодить)" + NL +
        "- Обработка ошибок через try/except" + NL +
        "- Логирование через print()" + NL +
        "- Не используй input()" + NL +
        "- README должен содержать: как получить ключи, куда вставить, как использовать" + NL +
        "- example_usage.py должен работать после вставки ключей" + NL + NL +
        format_instruction + NL +
        "=== ТЗ КЛИЕНТА ===" + NL + tz[:1500]
    )

    from ai import ask_ai
    response = ask_ai(prompt, model="gemini-3.5-flash-lite", max_retries=2)
    if not response:
        return None
    return _parse_files(response) or None
