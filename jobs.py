"""Парсинг Telegram-каналов с фриланс-заказами."""

import re
import requests
from datetime import datetime
from bs4 import BeautifulSoup


def _fetch_posts(channel, max_posts=5):
    """Скачивает и возвращает список (post_id, datetime_str, raw_text)."""
    url = f"https://t.me/s/{channel}"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    posts = soup.find_all("div", class_="tgme_widget_message")

    result = []
    for post in posts[-max_posts:]:
        text_div = post.find("div", class_="tgme_widget_message_text")
        if not text_div:
            continue
        time_tag = post.find("time")
        posted_at = time_tag.get("datetime") if time_tag else ""
        post_id = post.get("data-post", "")
        raw_text = text_div.get_text(separator="\n", strip=True)
        result.append((post_id, posted_at, raw_text))
    return result


def _parse_allgigs(raw_text, prefix):
    """Формат allgigs: подборки через эмодзи 📌."""
    text = raw_text.split("\U0001F516")[0]
    parts = text.split("\U0001F4CC")
    jobs = []
    for cat_idx, part in enumerate(parts[1:]):
        lines = [l.strip() for l in part.split("\n") if l.strip()]
        if not lines:
            continue
        category = lines[0]
        current_title = None
        current_desc = []
        job_idx = 0
        for line in lines[1:]:
            is_new_title = False
            if len(line) < 60 and not re.match(r"^(в |для |с |по |на |от |до |и )", line, re.IGNORECASE):
                if not re.match(r"^[\U0001F300-\U0001FAFF\U00002600-\U000027BF]+$", line):
                    is_new_title = True
            if is_new_title:
                if current_title is not None:
                    job_idx += 1
                    jobs.append({"job_uid": f"{prefix}_a{cat_idx}_{job_idx}", "category": category,
                                 "title": current_title, "description": " ".join(current_desc)})
                current_title = line
                current_desc = []
            else:
                if current_title is not None:
                    current_desc.append(line)
        if current_title is not None:
            job_idx += 1
            jobs.append({"job_uid": f"{prefix}_a{cat_idx}_{job_idx}", "category": category,
                         "title": current_title, "description": " ".join(current_desc)})
    return jobs


def _parse_python_jobs_ru(raw_text, prefix):
    """Формат python_jobs_ru: нумерованные вакансии через 'N.'."""
    jobs = []
    # Каждая вакансия начинается с "N." на отдельной строке
    parts = re.split(r"\n(?=\d+\.\s*$|\d+\.\s+[А-ЯA-Z])", raw_text)
    for idx, part in enumerate(parts):
        lines = [l.strip() for l in part.split("\n") if l.strip()]
        if len(lines) < 2:
            continue
        # Первая строка — что-то вроде "1." или "1. Python-разработчик"
        first = re.sub(r"^\d+\.\s*", "", lines[0]).strip()
        title = first if first else (lines[1] if len(lines) > 1 else "Без названия")
        description = " ".join(lines[1:])[:1000]
        jobs.append({"job_uid": f"{prefix}_j{idx}", "category": "Python",
                     "title": title[:200], "description": description})
    return jobs


def _parse_single_job(raw_text, prefix):
    """Универсальный парсер для каналов с 1 вакансией на пост."""
    lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
    if not lines:
        return []

    # Фильтр мусора: если нет признаков вакансии — пропускаем пост
    job_markers = ["title", "company", "position", "вакансия", "разработчик", "developer",
                   "engineer", "python", "django", "зарплата", "зп", "опыт", "requirements"]
    text_lower = raw_text.lower()
    if not any(m in text_lower for m in job_markers):
        return []

    # Отсекаем слишком короткие посты (реклама, анонсы)
    if len(raw_text) < 80:
        return []

    # Извлекаем Title: может быть "Title: X" ИЛИ "Title" на одной строке, ": X" на следующей
    title = None
    desc_parts = []
    i = 0
    while i < len(lines):
        line = lines[i]
        ll = line.lower()

        # Вариант 1: "Title: Python Developer"
        if ll.startswith("title") and ":" in line:
            val = line.split(":", 1)[1].strip()
            if val:
                title = val
                i += 1
                continue
        # Вариант 2: "Title" на строке, ": Python Developer" на следующей
        if ll == "title" and i + 1 < len(lines) and lines[i+1].startswith(":"):
            title = lines[i+1].lstrip(":").strip()
            i += 2
            continue

        # Пропускаем служебные лейблы
        if ll in ("published time", "company name", "grades", "location", "anywhere",
                  "remote", "forbidden locations", "job description", "tags"):
            i += 1
            continue

        # Строки с эмодзи-ссылками пропускаем
        if line.startswith(("👉", "👈", "#")):
            i += 1
            continue

        desc_parts.append(line)
        i += 1

    # Если title не нашли — берём первую осмысленную строку
    if not title:
        for line in lines:
            ll = line.lower()
            if not ll.startswith(("published", "company", "#", "👉", "👈", ":", "смотреть")):
                title = line.lstrip(":").strip()
                break

    if not title:
        title = lines[0]

    description = " ".join(desc_parts)[:1000]
    return [{"job_uid": f"{prefix}_s0", "category": "Python",
             "title": title[:200], "description": description}]


def fetch_jobs_from_channel(channel, max_posts=5):
    """Универсальный парсер: определяет формат канала по имени."""
    try:
        posts = _fetch_posts(channel, max_posts)
    except Exception as e:
        print(f"⚠ Не смог получить посты из {channel}: {e}")
        return []

    all_jobs = []
    for post_id, posted_at, raw_text in posts:
        prefix = post_id.replace("/", "_") or f"{channel}_{datetime.now().timestamp()}"

        if channel == "allgigs":
            jobs = _parse_allgigs(raw_text, prefix)
        elif channel == "python_jobs_ru":
            jobs = _parse_python_jobs_ru(raw_text, prefix)
        else:
            jobs = _parse_single_job(raw_text, prefix)

        for j in jobs:
            j["post_url"] = f"https://t.me/{post_id}"
            j["posted_at"] = posted_at

        all_jobs.extend(jobs)
    return all_jobs


def broadcast_to_all_users(use_ai_filter=True, min_score=6):
    """Парсит ВСЕ каналы и рассылает релевантные вакансии."""
    import time as time_module
    import database
    from core import bot

    channels = ["python_jobs_ru", "remote_python_jobs", "pythonrabota"]
    total_parsed = 0
    total_saved = 0

    for channel in channels:
        try:
            jobs = fetch_jobs_from_channel(channel, max_posts=3)
            if jobs:
                new = database.save_jobs(jobs, channel)
                total_parsed += len(jobs)
                total_saved += new
                print(f"📥 {channel}: parsed={len(jobs)}, saved_new={new}", flush=True)
        except Exception as e:
            print(f"⚠ Ошибка канала {channel}: {e}", flush=True)

    users = database.get_all_users_with_filters()
    sent_users = 0
    sent_jobs_total = 0
    ai_filtered_count = 0
    ai_error_count = 0

    for user_id, keywords in users:
        try:
            candidates = database.get_new_jobs_for_user(user_id, keywords, limit=8)
            if not candidates:
                continue

            if not use_ai_filter:
                approved = [(j[0], j[1], j[2], j[3], j[4], None, None) for j in candidates]
            else:
                from ai import evaluate_job_relevance
                approved = []
                for jid, cat, title, desc, url in candidates:
                    score, reason = evaluate_job_relevance(title, desc, keywords)
                    if score is None:
                        ai_error_count += 1
                        continue
                    if score >= min_score:
                        approved.append((jid, cat, title, desc, url, score, reason))
                    else:
                        ai_filtered_count += 1
                        database.mark_jobs_sent(user_id, [jid])
                    time_module.sleep(4)

            if not approved:
                continue

            lines = [f"🎯 Новые вакансии по фильтру '{keywords}' ({len(approved)}):\n"]
            job_ids = []
            for jid, cat, title, desc, url, score, reason in approved:
                job_ids.append(jid)
                header = f"[{cat}] {title}"
                if score is not None:
                    header += f"  ⭐ {score}/10"
                lines.append(header)
                lines.append(f"   {desc[:150]}...")
                if reason:
                    lines.append(f"   💡 {reason}")
                lines.append(f"   🔗 {url}\n")

            text = "\n".join(lines)
            for part in [text[i:i+4000] for i in range(0, len(text), 4000)]:
                try:
                    bot.send_message(user_id, part, disable_web_page_preview=True)
                except Exception as e:
                    print(f"⚠ Не смог отправить {user_id}: {e}")
                    break

            database.mark_jobs_sent(user_id, job_ids)
            sent_users += 1
            sent_jobs_total += len(job_ids)

        except Exception:
            import traceback
            print(f"🔥 Ошибка рассылки для {user_id}:\n{traceback.format_exc()}")

    return {
        "parsed": total_parsed, "saved": total_saved,
        "sent_users": sent_users, "sent_jobs": sent_jobs_total,
        "ai_filtered": ai_filtered_count, "ai_errors": ai_error_count
    }
