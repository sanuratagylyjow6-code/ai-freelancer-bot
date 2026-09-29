"""Изолированный запуск кода для проверки."""

import os
import sys
import uuid
import shutil
import subprocess
import tempfile


def test_code_safe(code, timeout=15):
    """Запускает код в изолированной папке без токенов.

    Возвращает dict: {ok, stdout, stderr, returncode, error}
    """
    # Уникальная временная папка
    tmpdir = os.path.join(tempfile.gettempdir(), "sandbox_" + uuid.uuid4().hex[:8])
    os.makedirs(tmpdir, exist_ok=True)

    filepath = os.path.join(tmpdir, "test_script.py")

    try:
        with open(filepath, "w") as f:
            f.write(code)

        # Минимальный env — без BOT_TOKEN, GEMINI_API_KEY и т.д.
        safe_env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": tmpdir,
            "HOME": tmpdir,
        }

        result = subprocess.run(
            [sys.executable, filepath],
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
                "error": "Timeout: код работал дольше " + str(timeout) + " сек (возможно, бесконечный цикл или ожидание ввода)"}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": "", "returncode": -1,
                "error": str(e)}
    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass


def quick_smoke_test(code, timeout=10):
    """Быстрая проверка: код должен запуститься и завершиться без ошибок.
    Пропускает блокирующие вызовы (polling, app.run)."""
    # Заменяем блокирующие вызовы на print — чтобы код не висел
    safe_code = code
    replacements = [
        ("bot.infinity_polling()", "print('would start polling')"),
        ("bot.polling()", "print('would start polling')"),
        ("bot.polling(none_stop=True)", "print('would start polling')"),
        ("app.run(", "print('would start flask') # app.run("),
        ("application.run_polling()", "print('would start polling')"),
    ]
    for old, new in replacements:
        safe_code = safe_code.replace(old, new)

    return test_code_safe(safe_code, timeout=timeout)
