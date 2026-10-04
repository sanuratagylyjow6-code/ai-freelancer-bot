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

    result_type = data.get('type', 'unknown')

    # ── QA-проход: Gemini перечитывает свой код и чинит баги ────────
    if files:                                                         # если есть файлы
        print("[MAKE] running self-critique...")                      # лог
        original = dict(files)                                        # бэкап
        try:                                                          # пробуем QA
            files = self_critique(files, tz)                          # критика
        except Exception as e:                                        # QA упал
            print("[MAKE] critique failed: " + str(e))                # лог
            files = original                                          # откат

        # ── Защита: проверяем синтаксис после QA ────────────────
        broken = []                                                   # список битых
        for name, code in files.items():                              # по файлам
            if name.endswith('.py'):                                  # только Python
                try:                                                  # пробуем парсить
                    import ast as _ast                                # локальный import
                    _ast.parse(code)                                  # парсим
                except SyntaxError as e:                              # битый код
                    broken.append(name + ": " + str(e))               # записываем
                    print("[MAKE] QA broke " + name + ": " + str(e))  # лог
        if broken:                                                    # если что-то битое
            print("[MAKE] reverting QA — syntax errors")              # лог
            files = original                                          # откат к оригиналу

    return {'type': result_type, 'files': files}
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


def self_critique(files_dict, tz, max_attempts=1):
    """QA-проход: Gemini ищет баги в своём коде и чинит их.

    Возвращает обновлённый files_dict. Если багов нет — исходный.
    """
    import json as _json                                             # локальный json
    import re as _re                                                 # локальный re
    if not files_dict:                                               # пустой вход
        return files_dict                                            # возвращаем как есть

    files_text = ""                                                  # аккумулятор
    for name, code in files_dict.items():                            # по файлам
        files_text += "\n=== " + name + " ===\n" + code + "\n"    # формат

    prompt = (                                                       # промпт QA
        "Ты — QA-инженер уровня senior. Проверь этот код на баги.\n\n"
        "ОБРАТИ ВНИМАНИЕ НА:\n"
        "1. Опечатки в strftime/strptime (например %5 вместо %m).\n"
        "2. Забытые импорты или неиспользуемые переменные.\n"
        "3. Необработанные edge-cases (пустой ответ, None, деление на 0).\n"
        "4. Несоответствие ТЗ клиента.\n"
        "5. Отсутствие валидации пользовательского ввода.\n\n"
        "ТЗ КЛИЕНТА:\n" + tz + "\n\n"
        "ТЕКУЩИЕ ФАЙЛЫ:" + files_text + "\n\n"
        "Верни ТОЛЬКО файлы, в которых нашёл баги, в формате JSON:\n"
        '{"files": {"main.py": "исправленный код"}}\n'
        "Если багов нет — верни {\"files\": {}}.\n"
    )

    raw = ask_ai(prompt)                                             # запрос к Gemini
    if not raw:                                                      # нет ответа
        return files_dict                                            # оригинал

    cleaned = _re.sub(r"^```(?:json)?\s*", "", raw.strip())         # чистим ```
    cleaned = _re.sub(r"\s*```$", "", cleaned)                      # чистим в конце

    try:                                                             # парсим
        data = _json.loads(cleaned)                                  # JSON
    except Exception as e:                                           # упало
        print("[CRITIQUE] parse failed: " + str(e))                  # лог
        return files_dict                                            # оригинал

    fixes = data.get("files", {})                                    # что починил
    if not fixes:                                                    # пусто
        print("[CRITIQUE] no bugs found")                            # лог
        return files_dict                                            # оригинал

    print("[CRITIQUE] fixed: " + ", ".join(fixes.keys()))            # лог
    merged = dict(files_dict)                                        # копия
    merged.update(fixes)                                             # заменяем починенные
    return merged                                                    # результат
