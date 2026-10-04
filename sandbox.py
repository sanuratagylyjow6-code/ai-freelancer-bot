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
        if ".." in name or name.startswith("/"):
            continue
        filepath = os.path.join(tmpdir, name)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        try:
            with open(filepath, "w") as f:
                f.write(code)
        except Exception:
            pass

    # Ставим зависимости из requirements (только whitelist)
    _install_requirements(files_dict, tmpdir)

    # Wrapper: запускает main_file как МОДУЛЬ (run_name != "__main__")
    # → блок if __name__ == "__main__" не срабатывает → бот не запускается
    wrapper_path = os.path.join(tmpdir, "_sandbox_wrapper.py")
    wrapper_code = (
        "import sys, os, runpy\n"
        "sys.path.insert(0, os.getcwd())\n"
        "try:\n"
        "    runpy.run_path(" + repr(main_file) + ", run_name='_sandbox_')\n"
        "    print('[SANDBOX] module loaded OK')\n"
        "except SystemExit as e:\n"
        "    print('[SANDBOX] SystemExit:', e.code)\n"
        "except Exception:\n"
        "    import traceback\n"
        "    traceback.print_exc()\n"
        "    sys.exit(1)\n"
    )
    with open(wrapper_path, "w") as wf:
        wf.write(wrapper_code)

    try:
        safe_env = os.environ.copy()
        safe_env["PYTHONPATH"] = tmpdir + os.pathsep + safe_env.get("PYTHONPATH", "")
        safe_env["HOME"] = tmpdir
        for secret_key in ["GEMINI_API_KEY", "GITHUB_TOKEN", "DATABASE_URL", "DB_PASSWORD"]:
            safe_env.pop(secret_key, None)
        # Фейковый токен, чтобы Bot(token=...) не падал при импорте
        safe_env["BOT_TOKEN"] = "1234567890:FAKE_TEST_TOKEN_NOT_REAL_AAAAAAAAA"

        result = subprocess.run(
            [sys.executable, "-u", wrapper_path],
            capture_output=True,
            timeout=timeout,
            env=safe_env,
            cwd=tmpdir,
            text=True,
        )

        return {
            "ok": result.returncode == 0,
            "stdout": (result.stdout or "")[:2000],
            "stderr": (result.stderr or "")[:2000],
            "returncode": result.returncode,
            "error": None,
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

def _prepare_project(files_dict, main_file):
    """Заглушка: с новым runpy-запуском блокировки не нужны,
    токен передаётся через env["BOT_TOKEN"]."""
    return dict(files_dict)


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
