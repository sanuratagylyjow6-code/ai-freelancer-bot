# ai.py — работа с Google Gemini API
# 6 функций: ask_ai, generate_full_project, edit_project,
#           run_code, auto_fix, set_model / get_current_model

import os
import time
import json
import re
import traceback
from google import genai
from config import AI_MODEL, MAX_ATTEMPTS

# Клиент создаётся один раз при импорте модуля
_client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY', ''))

# Глобальная переменная с текущей моделью
_current_model = AI_MODEL

def set_model(model_name):
    # Переключает модель Gemini, возвращает True/False
    global _current_model
    allowed = ['gemini-3.5-flash-lite', 'gemini-2.5-pro', 'gemini-flash-latest']
    if model_name in allowed:
        _current_model = model_name
        return True
    return False

def get_current_model():
    # Возвращает имя текущей модели
    return _current_model

def ask_ai(prompt, model=None, max_retries=3):
    # Отправляет промпт в Gemini, возвращает текст ответа
    m = model or _current_model
    for attempt in range(max_retries):
        try:
            resp = _client.models.generate_content(
                model=m, contents=prompt
            )
            return resp.text
        except Exception as e:
            print(f'⚠️ Gemini error (try {attempt+1}): {e}')
            time.sleep(4)
    return ''

def generate_full_project(tz, project_type=None, max_fix_attempts=2):
    # ⭐ ЯДРО: получает ТЗ, возвращает dict с файлами проекта
    # Возврат: {'type': '...', 'files': {'main.py': '...', ...}}

    # Системный промпт — объясняем Gemini, кто он и что делать
    system = '''Ты — универсальный Python-разработчик уровня senior.
Твоя задача: по ТЗ клиента создать РАБОЧИЙ проект на Python.

ПРАВИЛА СТРУКТУРЫ (обязательно):
1. Определи тип проекта САМ: bot, parser, api, website, automation,
   data, game, gui, documents, image, integration.
2. РАЗДЕЛЯЙ логику по файлам — НЕ пихай всё в main.py:
   • bot → main.py + handlers.py + database.py + config.py
   • parser → main.py + parser.py + config.py
   • api → main.py + routes.py + models.py + database.py
   • automation → main.py + tasks.py + config.py
3. Обязательные файлы: requirements.txt, README.md, .env.example.

ПРАВИЛА КАЧЕСТВА КОДА:
4. Обрабатывай сетевые/файловые ошибки через try/except.
5. Используй logging (не print) для логов.
6. Ключи/токены/URL — только через os.environ.get().
7. Валидируй пользовательский ввод (формат дат, чисел, команд).
8. Проверяй форматы strftime/strptime — не хардкодь даты.
9. Никаких заглушек: TODO, pass, not implemented.
10. Только реальные библиотеки (не выдумывай названия).

ПРАВИЛА README:
11. Секции обязательно: Требования, Установка, Запуск, Использование.
12. Примеры конкретные, с реальными командами.

ПРАВИЛА requirements.txt:
13. Только реально используемые пакеты, с версиями (==).

ПРАВИЛА .env.example:
14. Все переменные окружения, которые читает код.

ФОРМАТ ОТВЕТА — строго JSON, без markdown:
{"type": "bot", "files": {"main.py": "код...", "requirements.txt": "..."}}
'''

    # Собираем user-промпт с ТЗ клиента
    user = f'ТЗ клиента:\n{tz}\n\nСоздай проект. Верни JSON.'
    if project_type:
        user += f'\n(подсказка: это похоже на {project_type})'

    # Отправляем в Gemini
    raw = ask_ai(system + '\n\n' + user)
    if not raw:
        return {'type': 'unknown', 'files': {}}

    # Очищаем от ```json ... ``` если Gemini обернул
    cleaned = raw.strip()
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
    cleaned = re.sub(r'\s*```$', '', cleaned)

    # Парсим JSON
    try:
        data = json.loads(cleaned)
    except Exception as e:
        print(f'❌ JSON parse failed: {e}')
        print(f'Raw: {raw[:500]}')
        return {'type': 'unknown', 'files': {}}

    # Гарантируем обязательные файлы
    files = data.get('files', {})
    if 'requirements.txt' not in files:
        files['requirements.txt'] = '# см. README'
    if 'README.md' not in files:
        files['README.md'] = f'# Проект\n\n{tz}'

    return {'type': data.get('type', 'unknown'), 'files': files}
def edit_project(existing_files, tz_edit, max_fix_attempts=2):
    # Дорабатывает существующий проект по правкам клиента
    files_text = ''
    for name, code in existing_files.items():
        files_text += f'\n=== {name} ===\n{code}\n'

    prompt = f'''Ты — Python-разработчик.
Ниже — существующий проект. Внеси правки по запросу клиента.
НЕ ломай то, что уже работает. Верни ТОЛЬКО изменённые файлы
в формате JSON: {{"files": {{"main.py": "новый код"}}}}.

ТЕКУЩИЕ ФАЙЛЫ:{files_text}

ЗАПРОС КЛИЕНТА: {tz_edit}
'''
    raw = ask_ai(prompt)
    if not raw:
        return {}
    cleaned = re.sub(r'^```(?:json)?\s*', '', raw.strip())
    cleaned = re.sub(r'\s*```$', '', cleaned)
    try:
        data = json.loads(cleaned)
        return data.get('files', {})
    except Exception as e:
        print(f'❌ edit parse failed: {e}')
        return {}


def run_code(code_text, timeout=15):
    # Запускает код в отдельном процессе, возвращает stdout+stderr
    import subprocess, sys, tempfile
    with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False) as f:
        f.write(code_text)
        path = f.name
    try:
        r = subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=timeout)
        return {'ok': r.returncode == 0, 'stdout': r.stdout, 'stderr': r.stderr}
    except subprocess.TimeoutExpired:
        return {'ok': False, 'stdout': '', 'stderr': f'Timeout {timeout}s'}
    except Exception as e:
        return {'ok': False, 'stdout': '', 'stderr': str(e)}


def auto_fix(original_code, error_text, attempts=MAX_ATTEMPTS):
    # Просит Gemini починить код по тексту ошибки
    current = original_code
    for i in range(attempts):
        prompt = f'''Код упал с ошибкой:
ОШИБКА:
{error_text}

КОД:
{current}

Исправь. Верни ТОЛЬКО исправленный код без markdown.'''
        fixed = ask_ai(prompt)
        if not fixed:
            break
        fixed = re.sub(r'^```(?:python)?\s*', '', fixed.strip())
        fixed = re.sub(r'\s*```$', '', fixed)
        result = run_code(fixed)
        if result['ok']:
            return fixed
        current = fixed
        error_text = result['stderr']
    return current
