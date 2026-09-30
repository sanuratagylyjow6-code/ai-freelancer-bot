"""Парсинг источников заказов: Telegram-каналы + RSS-фиды бирж."""

import re
import html
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from bs4 import BeautifulSoup


# ============================================================
# ОБЩИЕ УТИЛИТЫ
# ============================================================

def _clean_html(text):
    """Убирает HTML-теги, раскодирует сущности, нормализует пробелы."""
    if not text:
        return ""
    clean = BeautifulSoup(text, "html.parser").get_text(separator=" ", strip=True)
    clean = html.unescape(clean)
    return re.sub(r"\s+", " ", clean).strip()


# ============================================================
# TELEGRAM-ИСТОЧНИКИ
# ============================================================

def _fetch_tg_posts(channel, max_posts=3):
    url = "https://t.me/s/" + channel
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
                    jobs.append({"job_uid": prefix + "_a" + str(cat_idx) + "_" + str(job_idx),
                                 "category": category, "title": current_title,
                                 "description": " ".join(current_desc)})
                current_title = line
                current_desc = []
            else:
                if current_title is not None:
                    current_desc.append(line)
        if current_title is not None:
            job_idx += 1
            jobs.append({"job_uid": prefix + "_a" + str(cat_idx) + "_" + str(job_idx),
                         "category": category, "title": current_title,
                         "description": " ".join(current_desc)})
    return jobs


def _parse_python_jobs_ru(raw_text, prefix):
    jobs = []
    parts = re.split(r"\n(?=\d+\.\s*$|\d+\.\s+[А-ЯA-Z])", raw_text)
    for idx, part in enumerate(parts):
        lines = [l.strip() for l in part.split("\n") if l.strip()]
        if len(lines) < 2:
            continue
        first = re.sub(r"^\d+\.\s*", "", lines[0]).strip()
        title = first if first else (lines[1] if len(lines) > 1 else "Без названия")
        description = " ".join(lines[1:])[:1000]
        jobs.append({"job_uid": prefix + "_j" + str(idx), "category": "Python",
                     "title": title[:200], "description": description})
    return jobs


def _parse_freelance_zakazy(raw_text, prefix):
    lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
    if not lines:
        return []
    title = None
    description = []
    budget = ""
    in_desc = False
    in_budget = False
    for line in lines:
        if line == "\U0001F4CC" and not title:
            continue
        if title is None and line != "\U0001F4CC" and line != "\U0001F4DD":
            if not line.startswith("\U0001F4B3"):
                title = line
                continue
        if line == "\U0001F4DD":
            in_desc = True
            in_budget = False
            continue
        if line == "\U0001F4B3":
            in_desc = False
            in_budget = True
            continue
        if in_desc:
            if line in ("\u3030\uFE0F", "\u3030", ""):
                continue
            description.append(line)
        elif in_budget:
            budget += " " + line
    budget = budget.replace("Бюджет:", "").replace("\u3030\uFE0F", "").strip()
    budget = " ".join(budget.split())
    if not title:
        return []
    full_desc = " ".join(description)
    if budget:
        full_desc = full_desc + " | Бюджет: " + budget
    return [{"job_uid": prefix + "_fz0", "category": "Фриланс",
             "title": title[:200], "description": full_desc[:1500]}]


def _parse_job_python(raw_text, prefix):
    lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
    if not lines:
        return []
    meaningful = [l for l in lines if not l.startswith("#")]
    if len(meaningful) < 2:
        return []
    company = meaningful[0]
    title = meaningful[1]
    desc_start = 2
    for i, line in enumerate(meaningful[2:], 2):
        if line.startswith("\u2611") or line.startswith("-") or line.startswith("Чем"):
            desc_start = i
            break
    description = " ".join(meaningful[desc_start:])
    return [{"job_uid": prefix + "_jp0", "category": "Python",
             "title": (title + " — " + company)[:200], "description": description[:1500]}]



def _parse_kwork_rss(items):
    """Парсер Kwork RSS: title, description (HTML), link."""
    jobs = []
    for idx, (guid, title, link, desc, pub) in enumerate(items):
        clean_title = _clean_html(title)
        clean_desc = _clean_html(desc)
        # Пытаемся вытащить бюджет из title (например, "за 8000 руб.")
        budget_match = re.search(r'за\s*([\d\s]+)\s*руб', title, re.IGNORECASE)
        budget = ""
        if budget_match:
            budget = " | Бюджет: " + budget_match.group(0).strip()
        jobs.append({
            "job_uid": _make_uid("kwork", guid, link, idx),
            "category": "Kwork",
            "title": clean_title[:200],
            "description": (clean_desc + budget)[:1500],
            "post_url": link,
            "posted_at": pub,
            "channel": "kwork",
        })
    return jobs

def _parse_single_job(raw_text, prefix):
    lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
    if not lines:
        return []
    job_markers = ["title", "company", "position", "вакансия", "разработчик",
                   "developer", "engineer", "python", "django", "зарплата",
                   "зп", "опыт", "requirements"]
    text_lower = raw_text.lower()
    if not any(m in text_lower for m in job_markers):
        return []
    if len(raw_text) < 80:
        return []
    title = None
    desc_parts = []
    i = 0
    while i < len(lines):
        line = lines[i]
        ll = line.lower()
        if ll.startswith("title") and ":" in line:
            val = line.split(":", 1)[1].strip()
            if val:
                title = val
                i += 1
                continue
        if ll == "title" and i + 1 < len(lines) and lines[i+1].startswith(":"):
            title = lines[i+1].lstrip(":").strip()
            i += 2
            continue
        if ll in ("published time", "company name", "grades", "location",
                  "anywhere", "remote", "forbidden locations",
                  "job description", "tags"):
            i += 1
            continue
        if line.startswith(("👉", "👈", "#")):
            i += 1
            continue
        desc_parts.append(line)
        i += 1
    if not title:
        for line in lines:
            ll = line.lower()
            if not ll.startswith(("published", "company", "#", "👉", "👈", ":", "смотреть")):
                title = line.lstrip(":").strip()
                break
    if not title:
        title = lines[0]
    return [{"job_uid": prefix + "_s0", "category": "Python",
             "title": title[:200], "description": " ".join(desc_parts)[:1000]}]


def fetch_from_telegram(channel, max_posts=3):
    try:
        posts = _fetch_tg_posts(channel, max_posts)
    except Exception as e:
        print("[TG] " + channel + ": " + str(e))
        return []
    all_jobs = []
    for post_id, posted_at, raw_text in posts:
        prefix = post_id.replace("/", "_") or channel
        if channel == "allgigs":
            jobs = _parse_allgigs(raw_text, prefix)
        elif channel == "python_jobs_ru":
            jobs = _parse_python_jobs_ru(raw_text, prefix)
        elif channel == "freelance_zakazy":
            jobs = _parse_freelance_zakazy(raw_text, prefix)
        elif channel == "job_python":
            jobs = _parse_job_python(raw_text, prefix)
        else:
            jobs = _parse_single_job(raw_text, prefix)
        for j in jobs:
            j["post_url"] = "https://t.me/" + post_id
            j["posted_at"] = posted_at
            j["channel"] = channel
        all_jobs.extend(jobs)
    return all_jobs


# ============================================================
# RSS-ИСТОЧНИКИ (БИРЖИ)
# ============================================================

def _fetch_rss_items(url, max_items=10):
    r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    root = ET.fromstring(r.text)
    items = root.findall(".//item")[:max_items]
    result = []
    for item in items:
        guid = item.findtext("guid") or item.findtext("link") or ""
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        desc = item.findtext("description") or ""
        pub = item.findtext("pubDate") or ""
        result.append((guid, title, link, desc, pub))
    return result


def _make_uid(prefix, guid, link, idx):
    src = guid or link or (prefix + "_" + str(idx))
    clean = re.sub(r"[^a-zA-Z0-9]", "", src)
    return prefix + "_" + clean[-40:]


def _parse_wwr_rss(items):
    """WeWorkRemotely: Title = 'Company: Role'."""
    jobs = []
    for idx, (guid, title, link, desc, pub) in enumerate(items):
        parts = title.split(":", 1)
        if len(parts) == 2:
            company = parts[0].strip()
            role = parts[1].strip()
            full_title = role + " — " + company
        else:
            full_title = title
        clean_desc = _clean_html(desc)
        jobs.append({
            "job_uid": _make_uid("wwr", guid, link, idx),
            "category": "Remote",
            "title": full_title[:200],
            "description": clean_desc[:1500],
            "post_url": link,
            "posted_at": pub,
            "channel": "weworkremotely",
        })
    return jobs


def _parse_freelancer_rss(items):
    """Freelancer.com: title, description, link."""
    jobs = []
    for idx, (guid, title, link, desc, pub) in enumerate(items):
        m = re.search(r"/projects/([^/]+)/", link)
        category = m.group(1).replace("-", " ").title() if m else "Freelance"
        if len(category) > 30:
            category = category[:30]
        clean_desc = _clean_html(desc)
        clean_title = _clean_html(title)
        jobs.append({
            "job_uid": _make_uid("fl", guid, link, idx),
            "category": category,
            "title": clean_title[:200],
            "description": clean_desc[:1500],
            "post_url": link,
            "posted_at": pub,
            "channel": "freelancer",
        })
    return jobs


def fetch_from_rss(url, parser_type, max_items=10):
    try:
        items = _fetch_rss_items(url, max_items)
    except Exception as e:
        print("[RSS] " + parser_type + ": " + str(e))
        return []
    if parser_type == "wwr":
        return _parse_wwr_rss(items)
    if parser_type == "freelancer":
        return _parse_freelancer_rss(items)
    if parser_type == "kwork":
        return _parse_kwork_rss(items)
    return []


# ============================================================
# ОБЩИЙ СБОРЩИК
# ============================================================

def fetch_all_sources():
    """Собирает вакансии из ВСЕХ источников."""
    all_jobs = []
    tg_channels = [
        "python_jobs_ru", "remote_python_jobs", "pythonrabota",
        "job_python", "freelance_zakazy", "devjobs",
    ]
    for ch in tg_channels:
        jobs = fetch_from_telegram(ch, max_posts=2)
        all_jobs.extend(jobs)
        print("[TG] " + ch + ": " + str(len(jobs)) + " вакансий", flush=True)

    rss_sources = [
        ("https://weworkremotely.com/categories/remote-programming-jobs.rss", "wwr"),
        ("https://www.freelancer.com/rss.xml", "freelancer"),
    ]
    for url, ptype in rss_sources:
        jobs = fetch_from_rss(url, ptype, max_items=10)
        all_jobs.extend(jobs)
        print("[RSS] " + ptype + ": " + str(len(jobs)) + " вакансий", flush=True)

    return all_jobs


# ============================================================
# РАССЫЛКА
# ============================================================


def fetch_all_sources_async():
    """Параллельно скачивает TG-каналы и RSS-фиды, потом парсит в sync."""
    from async_fetcher import run_async, fetch_tg_channels, fetch_rss_feeds
    from bs4 import BeautifulSoup

    # Список источников
    tg_channels = [
        "python_jobs_ru", "remote_python_jobs", "pythonrabota",
        "job_python", "freelance_zakazy", "devjobs",
    ]
    rss_sources = [
        ("https://weworkremotely.com/categories/remote-programming-jobs.rss", "wwr"),
        ("https://www.freelancer.com/rss.xml", "freelancer"),
    ]

    # Скачиваем ВСЁ параллельно
    tg_posts = run_async(fetch_tg_channels(tg_channels, max_posts=2))
    rss_texts = run_async(fetch_rss_feeds(rss_sources))

    all_jobs = []

    # Парсим TG (последовательно — быстро, это локальная работа)
    for ch, posts in tg_posts.items():
        for post in posts:
            try:
                text_div = post.find("div", class_="tgme_widget_message_text")
                if not text_div:
                    continue
                time_tag = post.find("time")
                posted_at = time_tag.get("datetime") if time_tag else ""
                post_id = post.get("data-post", "")
                raw_text = text_div.get_text(separator="\n", strip=True)
                prefix = post_id.replace("/", "_") or ch

                if ch == "python_jobs_ru":
                    jobs = _parse_python_jobs_ru(raw_text, prefix)
                elif ch == "freelance_zakazy":
                    jobs = _parse_freelance_zakazy(raw_text, prefix)
                elif ch == "job_python":
                    jobs = _parse_job_python(raw_text, prefix)
                else:
                    jobs = _parse_single_job(raw_text, prefix)

                for j in jobs:
                    j["post_url"] = "https://t.me/" + post_id
                    j["posted_at"] = posted_at
                    j["channel"] = ch
                all_jobs.extend(jobs)
            except Exception as e:
                print("[TG] " + ch + ": " + str(e), flush=True)

    # Парсим RSS
    for url, ptype in rss_sources:
        xml = rss_texts.get(ptype)
        if not xml:
            continue
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml)
            items = []
            for item in root.findall(".//item")[:10]:
                guid = item.findtext("guid") or item.findtext("link") or ""
                title = item.findtext("title") or ""
                link = item.findtext("link") or ""
                desc = item.findtext("description") or ""
                pub = item.findtext("pubDate") or ""
                items.append((guid, title, link, desc, pub))

            if ptype == "wwr":
                jobs = _parse_wwr_rss(items)
            elif ptype == "freelancer":
                jobs = _parse_freelancer_rss(items)
            else:
                jobs = []
            all_jobs.extend(jobs)
        except Exception as e:
            print("[RSS] " + ptype + ": " + str(e), flush=True)

    return all_jobs


def send_daily_summary(user_id, keywords):
    """Отправляет утреннюю сводку — топ-5 релевантных вакансий."""
    import database
    from core import bot

    jobs = database.get_recent_jobs_for_user_filtered(user_id, keywords, limit=5)
    if not jobs:
        return False

    lines = ["🌅 Утренняя сводка — топ-" + str(len(jobs)) + ":", ""]
    for jid, cat, title, desc, url in jobs:
        short_title = title[:80]
        lines.append("#" + str(jid) + " [" + cat + "] " + short_title)
        lines.append("   " + desc[:120] + "...")
        lines.append("   " + url)
        lines.append("")

    lines.append("Команды: /search <слово>, /budget <id>, /apply <id>")

    text = "\n".join(lines)
    try:
        bot.send_message(user_id, text, disable_web_page_preview=True)
        return True
    except Exception as e:
        print("Не смог отправить сводку " + str(user_id) + ": " + str(e), flush=True)
        return False


def maybe_send_daily_summaries():
    """Проверяет время и рассылает утренние сводки всем активным юзерам.

    Вызывается из /cron. Дешёвая проверка — если уже отправляли сегодня, пропускает.
    """
    from datetime import datetime, timezone
    import database

    now = datetime.now(timezone.utc)

    # Утреннее окно: 4:00-8:00 UTC = 9:00-13:00 по Туркменистану (UTC+5)
    if not (4 <= now.hour < 8):
        return {"skipped": "not morning"}

    today = now.strftime("%Y-%m-%d")
    users = database.get_all_users_with_filters()
    sent = 0

    for user_id, keywords in users:
        if database.check_summary_sent(user_id, today):
            continue
        if send_daily_summary(user_id, keywords):
            database.mark_summary_sent(user_id, today)
            sent += 1

    return {"date": today, "sent": sent}


def send_followup_reminders():
    """Раз в день напоминает юзерам о зависших вакансиях in_work > 3 дней."""
    from datetime import datetime, timezone
    import database
    from core import bot

    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")

    users = database.get_all_users_with_in_work()
    sent = 0

    for user_id in users:
        if database.check_followup_sent(user_id, today):
            continue

        stale = database.get_stale_jobs(user_id, days=3)
        if not stale:
            continue

        lines = ["⏰ Напоминание: " + str(len(stale)) + " вакансий в работе >3 дней:", ""]
        for jid, title, url, status, updated in stale:
            short_title = (title or "?")[:70]
            lines.append("#" + str(jid) + " " + short_title)
            lines.append("   🕐 Обновлено: " + (updated or "")[:16])
            lines.append("   " + (url or ""))
            lines.append("")

        lines.append("Сменить статус: /status <id> won/lost/archived")
        text = "\n".join(lines)

        try:
            bot.send_message(user_id, text, disable_web_page_preview=True)
            database.mark_followup_sent(user_id, today)
            sent += 1
        except Exception as e:
            print("Не смог отправить follow-up " + str(user_id) + ": " + str(e), flush=True)

    return {"date": today, "sent": sent}

def broadcast_to_all_users(use_ai_filter=True, min_score=6):
    """Парсит каналы и рассылает релевантные вакансии с inline-кнопками."""
    import time as time_module
    import database
    from core import bot
    from telebot import types

    jobs = fetch_all_sources_async()
    if not jobs:
        return {"parsed": 0, "saved": 0, "sent_users": 0, "sent_jobs": 0,
                "ai_filtered": 0, "ai_errors": 0}

    by_channel = {}
    for j in jobs:
        ch = j.get("channel", "unknown")
        by_channel.setdefault(ch, []).append(j)

    total_saved = 0
    for ch, ch_jobs in by_channel.items():
        saved = database.save_jobs(ch_jobs, ch)
        total_saved += saved

    users = database.get_all_users_with_filters()
    sent_users = 0
    sent_jobs_total = 0
    ai_filtered_count = 0
    ai_error_count = 0

    for user_id, keywords in users:
        try:
            candidates = database.get_new_jobs_for_user_filtered(user_id, keywords, limit=8)
            if not candidates:
                continue
            if not use_ai_filter:
                approved = [(j[0], j[1], j[2], j[3], j[4], None, None, None) for j in candidates]
            else:
                from ai import evaluate_job_relevance
                approved = []
                for jid, cat, title, desc, url in candidates:
                    score, reason = evaluate_job_relevance(title, desc, keywords)
                    if score is None:
                        ai_error_count += 1
                        continue
                    if score >= min_score:
                        # Оцениваем сложность только для релевантных вакансий
                        complexity = None
                        try:
                            complexity = evaluate_job_complexity(title, desc)
                        except Exception:
                            pass
                        time_module.sleep(4)
                        approved.append((jid, cat, title, desc, url, score, reason, complexity))
                    else:
                        ai_filtered_count += 1
                        database.mark_jobs_sent(user_id, [jid])
                    time_module.sleep(4)
            if not approved:
                continue
            job_ids = []
            for item in approved:
                jid, cat, title, desc, url, score, reason = item[0], item[1], item[2], item[3], item[4], item[5], item[6]
                complexity = item[7] if len(item) > 7 else None
                job_ids.append(jid)
                lines = ["#" + str(jid) + " [" + cat + "] " + title]
                lines.append("")
                lines.append(desc[:180] + "...")
                if score is not None:
                    lines.append("")
                    lines.append("\u2B50 " + str(score) + "/10")
                if reason:
                    lines.append("\U0001F4A1 " + reason)
                if complexity:
                    lines.append("\u23F1 Оценка: " + complexity)
                lines.append("")
                lines.append(url)
                text = "\n".join(lines)

                markup = types.InlineKeyboardMarkup()
                markup.row(
                    types.InlineKeyboardButton("\u2705 Откликнулся", callback_data="apply_" + str(jid)),
                    types.InlineKeyboardButton("\u274C Скрыть", callback_data="hide_" + str(jid)),
                )
                markup.row(
                    types.InlineKeyboardButton("\U0001F4DD Заметка", callback_data="note_" + str(jid)),
                )

                try:
                    bot.send_message(user_id, text, reply_markup=markup, disable_web_page_preview=True)
                except Exception as e:
                    print("Не смог отправить " + str(user_id) + ": " + str(e), flush=True)
                    break
            database.mark_jobs_sent(user_id, job_ids)
            sent_users += 1
            sent_jobs_total += len(job_ids)
        except Exception:
            import traceback
            print("Ошибка рассылки для " + str(user_id) + ":\n" + traceback.format_exc(), flush=True)

    return {
        "parsed": len(jobs), "saved": total_saved,
        "sent_users": sent_users, "sent_jobs": sent_jobs_total,
        "ai_filtered": ai_filtered_count, "ai_errors": ai_error_count
    }
