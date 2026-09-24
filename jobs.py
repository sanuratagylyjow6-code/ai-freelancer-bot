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
