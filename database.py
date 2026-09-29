"""Работа с PostgreSQL: пользователи и задачи."""

import psycopg2
from datetime import datetime
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD


def get_conn():
    """Возвращает новое соединение с PostgreSQL."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        sslmode="require"
    )


def init_db():
    """Создаёт таблицы users и tasks, если их ещё нет."""
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            SERIAL PRIMARY KEY,
            user_id       BIGINT UNIQUE,
            username      TEXT,
            first_seen    TEXT,
            message_count INTEGER DEFAULT 1
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id         SERIAL PRIMARY KEY,
            user_id    BIGINT,
            prompt     TEXT,
            code       TEXT,
            status     TEXT,
            error      TEXT,
            attempts   INTEGER DEFAULT 1,
            created_at TEXT
        )
    """)

    conn.commit()
    cursor.close()
    conn.close()


def save_user(user_id, username):
    conn = get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    cursor.execute("SELECT message_count FROM users WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()

    if row is None:
        cursor.execute(
            "INSERT INTO users (user_id, username, first_seen, message_count) VALUES (%s, %s, %s, 1)",
            (user_id, username, now)
        )
    else:
        cursor.execute(
            "UPDATE users SET message_count = %s, username = %s WHERE user_id = %s",
            (row[0] + 1, username, user_id)
        )

    conn.commit()
    cursor.close()
    conn.close()


def get_user_stats(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT username, first_seen, message_count FROM users WHERE user_id = %s",
        (user_id,)
    )
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result


def get_all_clients():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, first_seen, message_count FROM users ORDER BY message_count DESC")
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result


def save_task(user_id, prompt, code):
    conn = get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute(
        "INSERT INTO tasks (user_id, prompt, code, status, created_at) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (user_id, prompt, code, "pending", now)
    )
    task_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()
    return task_id


def update_task(task_id, status, error=None, attempts=1):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tasks SET status = %s, error = %s, attempts = %s WHERE id = %s",
        (status, error, attempts, task_id)
    )
    conn.commit()
    cursor.close()
    conn.close()


def get_user_tasks(user_id, limit=5):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, prompt, status, attempts, created_at FROM tasks WHERE user_id = %s ORDER BY id DESC LIMIT %s",
        (user_id, limit)
    )
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result


def init_jobs_table():
    """Создаёт таблицу found_jobs для найденных вакансий."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS found_jobs (
            id           SERIAL PRIMARY KEY,
            job_uid      TEXT UNIQUE,
            channel      TEXT,
            category     TEXT,
            title        TEXT,
            description  TEXT,
            post_url     TEXT,
            posted_at    TEXT,
            found_at     TEXT
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()


def save_jobs(jobs_list, channel):
    """Сохраняет вакансии. Пропускает дубликаты по (title, post_url)."""
    conn = get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_count = 0

    for job in jobs_list:
        try:
            # Проверка: есть ли уже такая вакансия по title + post_url
            cursor.execute(
                "SELECT id FROM found_jobs WHERE title = %s AND post_url = %s LIMIT 1",
                (job["title"], job.get("post_url", ""))
            )
            existing = cursor.fetchone()
            if existing:
                continue  # пропускаем дубликат

            cursor.execute("""
                INSERT INTO found_jobs (job_uid, channel, category, title, description, post_url, posted_at, found_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                job["job_uid"],
                channel,
                job["category"],
                job["title"],
                job["description"],
                job.get("post_url", ""),
                job.get("posted_at", ""),
                now
            ))
            new_count += 1
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
        except Exception as e:
            print("Ошибка сохранения: " + str(e))
            conn.rollback()

    conn.commit()
    cursor.close()
    conn.close()
    return new_count


def search_jobs(keyword, limit=20):
    """Ищет заказы по ключевому слову в title или description."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT category, title, description, post_url, posted_at
        FROM found_jobs
        WHERE (title ILIKE %s OR description ILIKE %s)
        ORDER BY id DESC
        LIMIT %s
    """, (f"%{keyword}%", f"%{keyword}%", limit))
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result


def init_jobs_table():
    """Создаёт таблицу found_jobs для найденных вакансий."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS found_jobs (
            id           SERIAL PRIMARY KEY,
            job_uid      TEXT UNIQUE,
            channel      TEXT,
            category     TEXT,
            title        TEXT,
            description  TEXT,
            post_url     TEXT,
            posted_at    TEXT,
            found_at     TEXT
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()


def save_jobs(jobs_list, channel):
    """Сохраняет новые вакансии. Возвращает количество НОВЫХ."""
    conn = get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_count = 0

    for job in jobs_list:
        try:
            cursor.execute("""
                INSERT INTO found_jobs (job_uid, channel, category, title, description, post_url, posted_at, found_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                job["job_uid"],
                channel,
                job["category"],
                job["title"],
                job["description"],
                job["post_url"],
                job["posted_at"],
                now
            ))
            new_count += 1
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
        except Exception as e:
            print(f"\u26A0 Ошибка сохранения: {e}")
            conn.rollback()

    conn.commit()
    cursor.close()
    conn.close()
    return new_count


def search_jobs(keyword, limit=20):
    """Ищет заказы по ключевому слову в title или description."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT category, title, description, post_url, posted_at
        FROM found_jobs
        WHERE (title ILIKE %s OR description ILIKE %s)
        ORDER BY id DESC
        LIMIT %s
    """, (f"%{keyword}%", f"%{keyword}%", limit))
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result


def init_filters_table():
    """Создаёт таблицу user_filters."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_filters (
            user_id    BIGINT PRIMARY KEY,
            keywords   TEXT,
            active     INTEGER DEFAULT 1,
            created_at TEXT
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()


def set_filter(user_id, keywords):
    """Сохраняет фильтр пользователя (создаёт или обновляет)."""
    conn = get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute("""
        INSERT INTO user_filters (user_id, keywords, active, created_at)
        VALUES (%s, %s, 1, %s)
        ON CONFLICT (user_id) DO UPDATE
        SET keywords = EXCLUDED.keywords, active = 1
    """, (user_id, keywords, now))
    conn.commit()
    cursor.close()
    conn.close()


def get_filter(user_id):
    """Возвращает строку с ключевыми словами или None."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT keywords FROM user_filters WHERE user_id = %s AND active = 1", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row[0] if row else None


def clear_filter(user_id):
    """Отключает фильтр (не удаляет запись)."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("UPDATE user_filters SET active = 0 WHERE user_id = %s", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()


def get_all_users_with_filters():
    """Возвращает список (user_id, keywords) для всех активных фильтров."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, keywords FROM user_filters WHERE active = 1")
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result


def find_new_jobs_for_keywords(keywords_string, limit=20):
    """Ищет вакансии по строке ключевых слов через запятую."""
    words = [w.strip().lower() for w in keywords_string.split(",") if w.strip()]
    if not words:
        return []
    conn = get_conn()
    cursor = conn.cursor()
    where_parts = []
    params = []
    for w in words:
        where_parts.append("(LOWER(title) LIKE %s OR LOWER(description) LIKE %s)")
        params.append(f"%{w}%")
        params.append(f"%{w}%")
    sql = f"SELECT category, title, description, post_url FROM found_jobs WHERE {' OR '.join(where_parts)} ORDER BY id DESC LIMIT %s"
    params.append(limit)
    cursor.execute(sql, params)
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result


def init_sent_table():
    """Создаёт таблицу: что мы уже отправили какому пользователю."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sent_notifications (
            id        SERIAL PRIMARY KEY,
            user_id   BIGINT,
            job_id    INTEGER,
            sent_at   TEXT,
            UNIQUE (user_id, job_id)
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()


def get_new_jobs_for_user(user_id, keywords_string, limit=10):
    """Возвращает вакансии по фильтру, которые этому юзеру ещё не отправляли."""
    words = [w.strip().lower() for w in keywords_string.split(",") if w.strip()]
    if not words:
        return []

    conn = get_conn()
    cursor = conn.cursor()
    where_parts = []
    params = [user_id]
    for w in words:
        where_parts.append("(LOWER(f.title) LIKE %s OR LOWER(f.description) LIKE %s)")
        params.append(f"%{w}%")
        params.append(f"%{w}%")

    sql = f"""
        SELECT f.id, f.category, f.title, f.description, f.post_url
        FROM found_jobs f
        WHERE ({' OR '.join(where_parts)})
          AND f.id NOT IN (
              SELECT job_id FROM sent_notifications WHERE user_id = %s
          )
        ORDER BY f.id DESC
        LIMIT %s
    """
    # Параметры: сначала для WHERE слова, потом user_id для подзапроса, потом limit
    full_params = params[1:] + [user_id, limit]
    cursor.execute(sql, full_params)
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result


def mark_jobs_sent(user_id, job_ids):
    """Помечает список вакансий как отправленные пользователю."""
    if not job_ids:
        return
    conn = get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    for jid in job_ids:
        try:
            cursor.execute(
                "INSERT INTO sent_notifications (user_id, job_id, sent_at) VALUES (%s, %s, %s)",
                (user_id, jid, now)
            )
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
    conn.commit()
    cursor.close()
    conn.close()


def init_projects_table():
    """Создаёт таблицу projects для сгенерированных проектов."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id         SERIAL PRIMARY KEY,
            user_id    BIGINT,
            ptype      TEXT,
            tz         TEXT,
            code       TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()


def save_project(user_id, ptype, tz, code, parent_id=None):
    """Сохраняет проект (или новую версию) и возвращает его id."""
    conn = get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute(
        "INSERT INTO projects (user_id, ptype, tz, code, created_at, parent_id) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (user_id, ptype, tz, code, now, parent_id)
    )
    pid = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()
    return pid


def get_user_projects(user_id, limit=10):
    """Список последних проектов пользователя."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, ptype, tz, created_at FROM projects WHERE user_id = %s ORDER BY id DESC LIMIT %s",
        (user_id, limit)
    )
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result


def get_project(pid, user_id):
    """Возвращает (ptype, tz, code) или None."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT ptype, tz, code FROM projects WHERE id = %s AND user_id = %s",
        (pid, user_id)
    )
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result


def get_project_with_parent(pid, user_id):
    """Возвращает (id, ptype, tz, code, parent_id) или None."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, ptype, tz, code, parent_id FROM projects WHERE id = %s AND user_id = %s",
        (pid, user_id)
    )
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result


def init_full_projects_table():
    """Таблица для многофайловых проектов."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS full_projects (
            id         SERIAL PRIMARY KEY,
            user_id    BIGINT,
            tz         TEXT,
            files_json TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()


def save_full_project(user_id, tz, files_dict):
    """Сохраняет многофайловый проект (files — dict {name: code})."""
    import json
    files_json = json.dumps(files_dict, ensure_ascii=False)
    conn = get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute(
        "INSERT INTO full_projects (user_id, tz, files_json, created_at) VALUES (%s, %s, %s, %s) RETURNING id",
        (user_id, tz, files_json, now)
    )
    pid = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()
    return pid


def get_user_full_projects(user_id, limit=10):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, tz, created_at FROM full_projects WHERE user_id = %s ORDER BY id DESC LIMIT %s",
        (user_id, limit)
    )
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result


def get_full_project(pid, user_id):
    """Возвращает dict {filename: code} или None."""
    import json
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT files_json FROM full_projects WHERE id = %s AND user_id = %s",
        (pid, user_id)
    )
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if not row:
        return None
    return json.loads(row[0])


# ============================================================
# СТАТИСТИКА ДЛЯ DASHBOARD
# ============================================================

def get_dashboard_stats():
    """Собирает всю статистику для дашборда."""
    conn = get_conn()
    cursor = conn.cursor()
    stats = {}

    # --- Вакансии ---
    cursor.execute("SELECT COUNT(*) FROM found_jobs")
    stats["jobs_total"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM found_jobs WHERE found_at::date = CURRENT_DATE")
    stats["jobs_today"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM found_jobs WHERE found_at::timestamp > NOW() - INTERVAL '7 days'")
    stats["jobs_week"] = cursor.fetchone()[0]

    # --- Топ каналов ---
    cursor.execute("""
        SELECT channel, COUNT(*) as cnt
        FROM found_jobs
        GROUP BY channel
        ORDER BY cnt DESC
        LIMIT 10
    """)
    stats["top_channels"] = cursor.fetchall()

    # --- AI-фильтр ---
    cursor.execute("SELECT COUNT(DISTINCT job_id) FROM sent_notifications")
    stats["jobs_sent"] = cursor.fetchone()[0]
    stats["jobs_filtered"] = stats["jobs_total"] - stats["jobs_sent"]

    # --- Отправки по пользователям ---
    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM sent_notifications")
    stats["users_notified"] = cursor.fetchone()[0]

    # --- Проекты ---
    cursor.execute("SELECT COUNT(*) FROM projects")
    stats["projects_total"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM full_projects")
    stats["projects_full"] = cursor.fetchone()[0]

    cursor.execute("""
        SELECT ptype, COUNT(*) FROM projects
        GROUP BY ptype ORDER BY COUNT(*) DESC
    """)
    stats["projects_by_type"] = cursor.fetchall()

    # --- Пользователи бота ---
    cursor.execute("SELECT COUNT(*) FROM users")
    stats["users_total"] = cursor.fetchone()[0]

    # --- Последние вакансии ---
    cursor.execute("""
        SELECT channel, category, title, post_url, found_at
        FROM found_jobs
        ORDER BY id DESC
        LIMIT 10
    """)
    stats["recent_jobs"] = cursor.fetchall()

    cursor.close()
    conn.close()
    return stats


def search_jobs_full(keyword, limit=20):
    """Поиск по title/description (регистронезависимый)."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, channel, category, title, description, post_url
        FROM found_jobs
        WHERE LOWER(title) LIKE %s OR LOWER(description) LIKE %s
        ORDER BY id DESC
        LIMIT %s
    """, ("%" + keyword.lower() + "%", "%" + keyword.lower() + "%", limit))
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result


def get_quick_stats():
    """Быстрая статистика для /stats."""
    conn = get_conn()
    cursor = conn.cursor()
    s = {}

    cursor.execute("SELECT COUNT(*) FROM found_jobs")
    s["total"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM found_jobs WHERE found_at::timestamp > NOW() - INTERVAL '1 day'")
    s["today"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM found_jobs WHERE found_at::timestamp > NOW() - INTERVAL '7 days'")
    s["week"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT job_id) FROM sent_notifications")
    s["sent"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM projects")
    s["projects"] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM full_projects")
    s["zips"] = cursor.fetchone()[0]

    cursor.execute("""
        SELECT channel, COUNT(*) FROM found_jobs
        GROUP BY channel ORDER BY COUNT(*) DESC LIMIT 3
    """)
    s["top_channels"] = cursor.fetchall()

    cursor.close()
    conn.close()
    return s


def parse_filter_keywords(keywords_string):
    """Разбирает строку фильтра на 3 части: include, exclude, lang."""
    parts = [p.strip().lower() for p in keywords_string.split(",") if p.strip()]
    include = []
    exclude = []
    lang = None

    for p in parts:
        if p.startswith("-"):
            exclude.append(p[1:].strip())
        elif p.startswith("lang:"):
            lang = p[5:].strip()
        else:
            include.append(p)

    return {"include": include, "exclude": exclude, "lang": lang}


def get_new_jobs_for_user_filtered(user_id, keywords_string, limit=8):
    """Ищет вакансии по include, отсеивает по exclude, фильтрует по lang."""
    f = parse_filter_keywords(keywords_string)
    include = f["include"]
    exclude = f["exclude"]
    lang = f["lang"]

    if not include and not lang:
        return []

    conn = get_conn()
    cursor = conn.cursor()

    where_parts = []
    params = []

    # Include: хотя бы одно слово в title/desc
    if include:
        inc_parts = []
        for w in include:
            inc_parts.append("(LOWER(f.title) LIKE %s OR LOWER(f.description) LIKE %s)")
            params.append("%" + w + "%")
            params.append("%" + w + "%")
        where_parts.append("(" + " OR ".join(inc_parts) + ")")

    # Language filter
    if lang == "en":
        where_parts.append("(f.title !~ '[А-Яа-яЁё]')")
    elif lang == "ru":
        where_parts.append("(f.title ~ '[А-Яа-яЁё]')")

    # Exclude: НИ одно слово не должно быть в title/desc
    for w in exclude:
        where_parts.append("(LOWER(f.title) NOT LIKE %s AND LOWER(f.description) NOT LIKE %s)")
        params.append("%" + w + "%")
        params.append("%" + w + "%")

    # Не отправлять повторно — user_id идёт СЮДА (в конец, а не в начало!)
    where_parts.append("f.id NOT IN (SELECT job_id FROM sent_notifications WHERE user_id = %s)")
    params.append(user_id)

    sql = ("SELECT f.id, f.category, f.title, f.description, f.post_url "
           "FROM found_jobs f WHERE " + " AND ".join(where_parts) +
           " ORDER BY f.id DESC LIMIT %s")
    params.append(limit)

    cursor.execute(sql, params)
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result


def save_note(user_id, job_id, note):
    conn = get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute("""
        INSERT INTO job_notes (user_id, job_id, note, created_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id, job_id) DO UPDATE
        SET note = EXCLUDED.note
    """, (user_id, job_id, note, now))
    conn.commit()
    cursor.close()
    conn.close()


def get_user_notes(user_id, limit=20):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT n.job_id, n.note, n.created_at, f.title, f.post_url
        FROM job_notes n
        LEFT JOIN found_jobs f ON f.id = n.job_id
        WHERE n.user_id = %s
        ORDER BY n.id DESC LIMIT %s
    """, (user_id, limit))
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result


def get_job_by_id(job_id):
    """Возвращает вакансию по ID: (id, channel, category, title, description, post_url)."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, channel, category, title, description, post_url
        FROM found_jobs WHERE id = %s
    """, (job_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result


def get_chart_data():
    """Данные для графиков: динамика по дням, распределение score, каналы."""
    conn = get_conn()
    cursor = conn.cursor()
    data = {}

    # 1. Вакансии за 7 дней (для линейного графика)
    cursor.execute("""
        SELECT DATE(found_at::timestamp) AS d, COUNT(*) 
        FROM found_jobs
        WHERE found_at::timestamp > NOW() - INTERVAL '7 days'
        GROUP BY d ORDER BY d
    """)
    data["daily"] = [(str(r[0]), r[1]) for r in cursor.fetchall()]

    # 2. Топ-7 каналов (для bar-chart)
    cursor.execute("""
        SELECT channel, COUNT(*) FROM found_jobs
        GROUP BY channel ORDER BY COUNT(*) DESC LIMIT 7
    """)
    data["channels"] = cursor.fetchall()

    # 3. Распределение AI-оценок через sent_notifications (только отправленные = высокие)
    cursor.execute("SELECT COUNT(*) FROM sent_notifications")
    data["sent_total"] = cursor.fetchone()[0]

    # 4. Сколько новых vs старых
    cursor.execute("SELECT COUNT(*) FROM found_jobs WHERE found_at::timestamp > NOW() - INTERVAL '1 day'")
    data["new_today"] = cursor.fetchone()[0]

    cursor.close()
    conn.close()
    return data


def set_job_status(user_id, job_id, status):
    """Устанавливает статус вакансии. UPSERT."""
    conn = get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute("""
        INSERT INTO job_statuses (user_id, job_id, status, updated_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id, job_id) DO UPDATE
        SET status = EXCLUDED.status, updated_at = EXCLUDED.updated_at
    """, (user_id, job_id, status, now))
    conn.commit()
    cursor.close()
    conn.close()


def get_job_status(user_id, job_id):
    """Возвращает статус вакансии или None."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT status, updated_at FROM job_statuses WHERE user_id = %s AND job_id = %s",
        (user_id, job_id)
    )
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result


def get_jobs_by_status(user_id, status=None, limit=20):
    """Возвращает вакансии с указанным статусом (или все, если None)."""
    conn = get_conn()
    cursor = conn.cursor()
    if status:
        cursor.execute("""
            SELECT s.job_id, s.status, s.updated_at, f.title, f.post_url
            FROM job_statuses s
            LEFT JOIN found_jobs f ON f.id = s.job_id
            WHERE s.user_id = %s AND s.status = %s
            ORDER BY s.id DESC LIMIT %s
        """, (user_id, status, limit))
    else:
        cursor.execute("""
            SELECT s.job_id, s.status, s.updated_at, f.title, f.post_url
            FROM job_statuses s
            LEFT JOIN found_jobs f ON f.id = s.job_id
            WHERE s.user_id = %s
            ORDER BY s.id DESC LIMIT %s
        """, (user_id, limit))
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result


def save_user_file(user_id, filename, content, file_type):
    conn = get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute("""
        INSERT INTO user_files (user_id, filename, content, file_type, uploaded_at)
        VALUES (%s, %s, %s, %s, %s)
    """, (user_id, filename, content, file_type, now))
    conn.commit()
    fid = cursor.lastrowid
    cursor.close()
    conn.close()
    return fid


def get_latest_user_file(user_id):
    """Возвращает последний файл юзера: (filename, content, file_type, uploaded_at) или None."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT filename, content, file_type, uploaded_at
        FROM user_files
        WHERE user_id = %s
        ORDER BY id DESC LIMIT 1
    """, (user_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result


def clear_user_files(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_files WHERE user_id = %s", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()


def save_draft(user_id, brief=None, questions=None, answers=None, full_tz=None, state=None):
    """Сохраняет черновик ТЗ. Обновляет только переданные поля."""
    conn = get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Проверяем, есть ли уже
    cursor.execute("SELECT id FROM tz_drafts WHERE user_id = %s", (user_id,))
    exists = cursor.fetchone()

    if not exists:
        cursor.execute("""
            INSERT INTO tz_drafts (user_id, brief, questions, answers, full_tz, state, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (user_id, brief or "", questions or "", answers or "", full_tz or "", state or "drafting", now))
    else:
        updates = []
        params = []
        if brief is not None:
            updates.append("brief = %s"); params.append(brief)
        if questions is not None:
            updates.append("questions = %s"); params.append(questions)
        if answers is not None:
            updates.append("answers = %s"); params.append(answers)
        if full_tz is not None:
            updates.append("full_tz = %s"); params.append(full_tz)
        if state is not None:
            updates.append("state = %s"); params.append(state)
        updates.append("updated_at = %s"); params.append(now)
        params.append(user_id)
        cursor.execute("UPDATE tz_drafts SET " + ", ".join(updates) + " WHERE user_id = %s", params)

    conn.commit()
    cursor.close()
    conn.close()


def get_draft(user_id):
    """Возвращает (brief, questions, answers, full_tz, state) или None."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT brief, questions, answers, full_tz, state
        FROM tz_drafts WHERE user_id = %s
    """, (user_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result


def clear_draft(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tz_drafts WHERE user_id = %s", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()
