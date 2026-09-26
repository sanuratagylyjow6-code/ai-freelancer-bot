"""Парсинг Telegram-каналов с фриланс-заказами."""

import re
import requests
from datetime import datetime
from bs4 import BeautifulSoup


def parse_post_text(text, job_uid_prefix):
    """Парсит ОДИН пост → список вакансий."""
    text = text.split("\U0001F516")[0]
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
                    jobs.append({
                        "job_uid": f"{job_uid_prefix}_{cat_idx}_{job_idx}",
                        "category": category,
                        "title": current_title,
                        "description": " ".join(current_desc)
                    })
                current_title = line
                current_desc = []
            else:
                if current_title is not None:
                    current_desc.append(line)

        if current_title is not None:
            job_idx += 1
            jobs.append({
                "job_uid": f"{job_uid_prefix}_{cat_idx}_{job_idx}",
                "category": category,
                "title": current_title,
                "description": " ".join(current_desc)
            })

    return jobs


def fetch_jobs_from_channel(channel="allgigs", max_posts=5):
    """Скачивает и парсит последние N постов из канала."""
    url = f"https://t.me/s/{channel}"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    posts = soup.find_all("div", class_="tgme_widget_message")

    all_jobs = []
    for post in posts[-max_posts:]:
        text_div = post.find("div", class_="tgme_widget_message_text")
        if not text_div:
            continue

        time_tag = post.find("time")
        posted_at = time_tag.get("datetime") if time_tag else ""
        post_id = post.get("data-post", "")
        post_url = f"https://t.me/{post_id}" if post_id else ""

        prefix = post_id.replace("/", "_") or f"{channel}_{datetime.now().timestamp()}"
        raw_text = text_div.get_text(separator="\n", strip=True)

        jobs = parse_post_text(raw_text, prefix)
        for j in jobs:
            j["post_url"] = post_url
            j["posted_at"] = posted_at

        all_jobs.extend(jobs)

    return all_jobs


def broadcast_to_all_users(use_ai_filter=True, min_score=6):
    """Парсит канал и рассылает релевантные вакансии с AI-фильтром."""
    import time as time_module
    import database
    from core import bot

    jobs = fetch_jobs_from_channel("allgigs", max_posts=3)
    if not jobs:
        return {"parsed": 0, "saved": 0, "sent_users": 0, "sent_jobs": 0, "ai_filtered": 0, "ai_errors": 0}

    new_saved = database.save_jobs(jobs, "allgigs")

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
                        # ИИ недоступен — НЕ отправляем (лучше пропустить)
                        ai_error_count += 1
                        print(f"⏭ Пропущено (ИИ недоступен): {title[:60]}", flush=True)
                        continue

                    if score >= min_score:
                        approved.append((jid, cat, title, desc, url, score, reason))
                    else:
                        ai_filtered_count += 1
                        database.mark_jobs_sent(user_id, [jid])

                    # Пауза 4 сек между запросами = ~15 в минуту (лимит Free)
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
        "parsed": len(jobs),
        "saved": new_saved,
        "sent_users": sent_users,
        "sent_jobs": sent_jobs_total,
        "ai_filtered": ai_filtered_count,
        "ai_errors": ai_error_count
    }
