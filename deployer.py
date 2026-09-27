"""Автоматический деплой проектов на GitHub + Render."""

import os
import base64
import requests


GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "")


def _gh_headers():
    return {
        "Authorization": "token " + GITHUB_TOKEN,
        "Accept": "application/vnd.github+json",
    }


def create_repo(repo_name, description=""):
    """Создаёт публичный репозиторий. Возвращает URL или None."""
    data = {
        "name": repo_name,
        "description": description,
        "private": False,
        "auto_init": False,
    }
    r = requests.post("https://api.github.com/user/repos",
                      json=data, headers=_gh_headers(), timeout=15)
    if r.status_code == 201:
        return r.json()["html_url"]
    if r.status_code == 422:
        # Репо уже существует — используем существующий
        return "https://github.com/" + GITHUB_USERNAME + "/" + repo_name
    print("GitHub API create: " + str(r.status_code) + " " + r.text[:150])
    return None


def upload_file(repo_name, file_path, content, first_file=False):
    """Загружает файл в репо. При первой загрузке ветка создаётся автоматически."""
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    data = {
        "message": "Add " + file_path,
        "content": encoded,
    }
    if not first_file:
        data["branch"] = "main"
    url = ("https://api.github.com/repos/" + GITHUB_USERNAME + "/" +
           repo_name + "/contents/" + file_path)
    r = requests.put(url, json=data, headers=_gh_headers(), timeout=15)
    return r.status_code in (200, 201)


def make_render_yaml(project_type):
    """Генерирует render.yaml — манифест для деплоя на Render."""
    if project_type == "bot":
        start_cmd = "python bot.py"
    else:
        start_cmd = "python main.py"

    return (
        "services:\n"
        "  - type: web\n"
        "    name: ai-freelancer-generated\n"
        "    runtime: python\n"
        "    plan: free\n"
        "    buildCommand: pip install -r requirements.txt\n"
        "    startCommand: " + start_cmd + "\n"
        "    envVars:\n"
        "      - key: BOT_TOKEN\n"
        "        sync: false\n"
        "      - key: GEMINI_API_KEY\n"
        "        sync: false\n"
    )


def make_deploy_readme(project_tz, repo_url):
    """README с кнопкой Deploy to Render."""
    deploy_url = "https://render.com/deploy?repo=" + repo_url
    return (
        "# Сгенерированный проект\n\n"
        "**ТЗ:** " + project_tz + "\n\n"
        "## Быстрый деплой\n\n"
        "1. Нажми кнопку ниже.\n"
        "2. Авторизуйся в Render (если ещё нет аккаунта).\n"
        "3. Введи `BOT_TOKEN` (получить у @BotFather).\n"
        "4. Дождись билда ~2 минуты.\n\n"
        "[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](" + deploy_url + ")\n\n"
        "## Локальный запуск\n\n"
        "```bash\n"
        "pip install -r requirements.txt\n"
        "python bot.py\n"
        "```\n"
    )


def deploy_project(repo_name, files_dict, project_tz, project_type="bot"):
    """Полный цикл: создать репо → залить файлы → вернуть URL.

    Возвращает dict:
        {"ok": True, "repo_url": ..., "deploy_url": ..., "uploaded": N}
        или {"ok": False, "error": "..."}
    """
    if not GITHUB_TOKEN or not GITHUB_USERNAME:
        return {"ok": False, "error": "GITHUB_TOKEN или GITHUB_USERNAME не заданы"}

    # 1. Создаём репо
    repo_url = create_repo(repo_name, description=project_tz[:100])
    if not repo_url:
        return {"ok": False, "error": "Не смог создать репозиторий"}

    # 2. Готовим файлы (добавляем render.yaml и README с кнопкой)
    files_to_upload = dict(files_dict)
    files_to_upload["render.yaml"] = make_render_yaml(project_type)
    files_to_upload["README.md"] = make_deploy_readme(project_tz, repo_url)

    # 3. Загружаем
    uploaded = 0
    first = True
    for path, content in files_to_upload.items():
        if upload_file(repo_name, path, content, first_file=first):
            uploaded += 1
            first = False

    deploy_url = "https://render.com/deploy?repo=" + repo_url
    return {
        "ok": True,
        "repo_url": repo_url,
        "deploy_url": deploy_url,
        "uploaded": uploaded,
        "total": len(files_to_upload),
    }
