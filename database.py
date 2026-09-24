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
