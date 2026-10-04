"""Изолированный запуск кода для проверки."""

import os
import sys
import uuid
import shutil
import subprocess
import tempfile


# ── Whitelist безопасных пакетов (Render Free 512MB) ────────────────────────
SAFE_PACKAGES = {
    "aiogram", "python-telegram-bot", "pytelegrambotapi", "telebot",
    "python-dotenv", "dotenv", "apscheduler",
    "requests", "httpx", "beautifulsoup4", "bs4", "lxml",
    "flask", "fastapi", "uvicorn", "jinja2",
    "sqlalchemy", "pydantic", "openpyxl", "pillow",
    "schedule", "pypdf", "gspread", "pandas", "numpy",
    "python-dateutil", "pytz", "colorama", "rich",
}


def _install_requirements(files_dict, tmpdir):
    """Ставит пакеты из requirements.txt — только из whitelist."""
    req = files_dict.get("requirements.txt", "")
    if not req:
        return
    to_install = []
    for line in req.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Отрезаем версию: "aiogram==3.15.0" → "aiogram"
        name = line
        for sep in ["==", ">=", "<=", "~=", "!=", ">", "<"]:
            if sep in name:
                name = name.split(sep)[0]
                break
        name = name.strip().lower()
        if name in SAFE_PACKAGES:
            to_install.append(name)
    if not to_install:
        return
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q",
             "--no-warn-script-location", *to_install],
            capture_output=True, timeout=90, text=True,
        )
    except Exception:
        pass


def _run_in_tmpdir(files_dict, main_file, timeout):
    """Внутренняя: распаковывает все файлы и запускает main_file."""
    tmpdir = os.path.join(tempfile.gettempdir(), "sandbox_" + uuid.uuid4().hex[:8])
    os.makedirs(tmpdir, exist_ok=True)

    # Записываем ВСЕ файлы проекта
    for name, code in files_dict.items():
        # Защита: не пишем за пределы tmpdir
        if ".." in name or name.startswith("/"):
            continue
        filepath = os.path.join(tmpdir, name)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        try:
            with open(filepath, "w") as f:
                f.write(code)
        except Exception:
            pass

    _install_requirements(files_dict, tmpdir)

    main_path = os.path.join(tmpdir, main_file)

    try:
        # Наследуем env родителя (чтобы найти site-packages) + добавляем tmpdir
        safe_env = os.environ.copy()
        safe_env["PYTHONPATH"] = tmpdir + os.pathsep + safe_env.get("PYTHONPATH", "")
        safe_env["HOME"] = tmpdir
        # Убираем возможные секреты, чтобы код не мог их прочитать
        for secret_key in ["BOT_TOKEN", "GEMINI_API_KEY", "GITHUB_TOKEN", "DATABASE_URL"]:
            safe_env.pop(secret_key, None)

        result = subprocess.run(
            [sys.executable, main_path],
            capture_output=True,
            timeout=timeout,
            env=safe_env,
            cwd=tmpdir,
            text=True
        )

        return {
            "ok": result.returncode == 0,
            "stdout": (result.stdout or "")[:2000],
            "stderr": (result.stderr or "")[:2000],
            "returncode": result.returncode,
            "error": None
        }

    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "", "returncode": -1,
                "error": "Timeout: код работал дольше " + str(timeout) + " сек"}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": "", "returncode": -1,
                "error": str(e)}
    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass


def test_code_safe(code, timeout=15):
    """Запускает один файл (для обратной совместимости)."""
    return _run_in_tmpdir({"test_script.py": code}, "test_script.py", timeout)


def _prepare_project(files_dict, main_file):
    """Заменяет блокирующие вызовы и плейсхолдеры токенов."""
    import re

    # Блокирующие вызовы → в print
    blocking = [
        ("bot.infinity_polling()", "print('would start polling')"),
        ("bot.polling(none_stop=True)", "print('would start polling')"),
        ("bot.polling()", "print('would start polling')"),
        ("application.run_polling()", "print('would start polling')"),
        ("app.run(", "# app.run("),
        ("await dp.start_polling(bot)", "print('would start polling')"),
        ("await dp.start_polling(", "# await dp.start_polling("),
        ("dp.start_polling(bot)", "print('would start polling')"),
        ("dp.start_polling(", "# dp.start_polling("),
        ("bot.run_polling()", "print('would start polling')"),
        ("executor.start_polling(dp", "# executor.start_polling(dp"),
        ("scheduler.start()", "# scheduler.start()"),
        ("await asyncio.Event().wait()", "print('would wait forever')"),
    ]

    # Подмена плейсхолдеров токена
    # Валидный формат: "<10 цифр>:<35 символов>"
    FAKE_TOKEN = "1234567890:FAKE_TEST_TOKEN_NOT_REAL_AAAAAAAAA"

    prepared = {}
    for name, code in files_dict.items():
        new_code = code

        # 1) Блокирующие вызовы
        for old, new in blocking:
            new_code = new_code.replace(old, new)

        # 2) Плейсхолдеры токенов — все варианты, что генерирует Gemini
        placeholders = [
            '"YOUR_BOT_TOKEN_HERE"',
            "'YOUR_BOT_TOKEN_HERE'",
            '"YOUR_BOT_TOKEN"',
            "'YOUR_BOT_TOKEN'",
            '"TOKEN_HERE"',
            "'TOKEN_HERE'",
            '"YOUR_TOKEN"',
            "'YOUR_TOKEN'",
            '"ВАШ_ТОКЕН"',
            "'ВАШ_ТОКЕН'",
        ]
        for ph in placeholders:
            new_code = new_code.replace(ph, '"' + FAKE_TOKEN + '"')

        # 3) Регуляркой ловим остальные плейсхолдеры
        new_code = re.sub(
            r'(?i)(["\'])YOUR[_A-Z]*BOT[_A-Z]*TOKEN[_A-Z]*(["\'])',
            '"' + FAKE_TOKEN + '"',
            new_code
        )

        # 4) os.getenv("BOT_TOKEN", "плейсхолдер") → подменяем дефолт
        new_code = re.sub(
            r'(getenv\(["\']BOT_TOKEN["\'],\s*)(["\'])[^"\']*\2',
            r'\1"' + FAKE_TOKEN + '"',
            new_code
        )

        prepared[name] = new_code
    return prepared


def test_project_safe(files_dict, main_file, timeout=15):
    """Запускает многофайловый проект в sandbox."""
    prepared = _prepare_project(files_dict, main_file)
    return _run_in_tmpdir(prepared, main_file, timeout)


def quick_smoke_test(code, timeout=10):
    """Обратная совместимость: запускает один файл."""
    prepared = _prepare_project({"test_script.py": code}, "test_script.py")
    return _run_in_tmpdir(prepared, "test_script.py", timeout)


def run_pytest(files_dict, timeout=30):
    """Запускает pytest в папке проекта. Возвращает dict с результатом."""
    import subprocess
    tmpdir = os.path.join(tempfile.gettempdir(), "pytest_" + uuid.uuid4().hex[:8])
    os.makedirs(tmpdir, exist_ok=True)

    # Пишем все файлы
    for name, code in files_dict.items():
        if ".." in name or name.startswith("/"):
            continue
        filepath = os.path.join(tmpdir, name)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        try:
            with open(filepath, "w") as f:
                f.write(code)
        except Exception:
            pass

    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = tmpdir + os.pathsep + env.get("PYTHONPATH", "")
        env["HOME"] = tmpdir
        for k in ["BOT_TOKEN", "GEMINI_API_KEY", "GITHUB_TOKEN", "DB_PASSWORD"]:
            env.pop(k, None)

        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-v", "--tb=short", "--no-header"],
            capture_output=True,
            timeout=timeout,
            env=env,
            cwd=tmpdir,
            text=True
        )

        passed = result.returncode == 0
        stdout = (result.stdout or "")[:3000]
        stderr = (result.stderr or "")[:2000]

        # Объединённый вывод — pytest может писать и туда, и сюда
        full_output = stdout + chr(10) + stderr

        # Ищем сводку вида "5 passed" / "3 failed, 2 passed"
        import re
        summary = ""
        m = re.search(r"(\d+\s+(?:passed|failed|error)[^\n]*)", full_output)
        if m:
            summary = m.group(1)[:120]

        return {
            "ok": passed,
            "stdout": stdout,
            "stderr": stderr,
            "full_output": full_output[:4000],
            "summary": summary,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "", "summary": "Timeout (30с)",
                "returncode": -1}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e), "summary": "Ошибка запуска",
                "returncode": -1}
    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass
