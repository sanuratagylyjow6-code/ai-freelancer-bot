"""Изолированный запуск кода для проверки."""

import os
import sys
import uuid
import shutil
import subprocess
import tempfile


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

    main_path = os.path.join(tmpdir, main_file)

    try:
        safe_env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": tmpdir,
            "HOME": tmpdir,
        }

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
    """Заменяет блокирующие вызовы, чтобы код не висел."""
    replacements = [
        ("bot.infinity_polling()", "print('would start polling')"),
        ("bot.polling(none_stop=True)", "print('would start polling')"),
        ("bot.polling()", "print('would start polling')"),
        ("application.run_polling()", "print('would start polling')"),
        ("app.run(", "# app.run("),
    ]
    prepared = {}
    for name, code in files_dict.items():
        new_code = code
        for old, new in replacements:
            new_code = new_code.replace(old, new)
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
