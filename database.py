"""Работа с базой данных SQLite: пользователи и задачи."""

import sqlite3
from datetime import datetime
from config import DB_PATH


def get_conn():
    """Возвращает свежее соединение с БД."""
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    """Создаёт таблицы users и tasks, если их ещё нет."""
    conn = get_conn()
    cursor = conn.cursor()

    # SQL-запрос 1: таблица пользователей
    # id            - уникальный номер строки, ставится автоматически
    # user_id       - ID пользователя в Telegram (не повторяется)
    # username      - имя из профиля
    # first_seen    - дата первого обращения
    # message_count - сколько сообщений прислал
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER UNIQUE,
            username      TEXT,
            first_seen    TEXT,
            message_count INTEGER DEFAULT 1
        )
    """)

    # SQL-запрос 2: таблица задач (для /run и /code)
    # status: "pending" / "success" / "error"
    # attempts: сколько попыток потребовалось (1, 2, 3...)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            prompt     TEXT,
            code       TEXT,
            status     TEXT,
            error      TEXT,
            attempts   INTEGER DEFAULT 1,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


def save_user(user_id, username):
    """Сохраняет нового пользователя или обновляет счётчик у существующего."""
    conn = get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Проверяем, есть ли уже такой пользователь
    cursor.execute(
        "SELECT message_count FROM users WHERE user_id = ?",
        (user_id,)
    )
    row = cursor.fetchone()

    if row is None:
        # Новый пользователь — вставляем
        cursor.execute(
            "INSERT INTO users (user_id, username, first_seen, message_count) VALUES (?, ?, ?, 1)",
            (user_id, username, now)
        )
    else:
        # Уже есть — увеличиваем счётчик и обновляем имя
        cursor.execute(
            "UPDATE users SET message_count = ?, username = ? WHERE user_id = ?",
            (row[0] + 1, username, user_id)
        )

    conn.commit()
    conn.close()


def get_user_stats(user_id):
    """Возвращает кортеж (username, first_seen, message_count) или None."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT username, first_seen, message_count FROM users WHERE user_id = ?",
        (user_id,)
    )
    result = cursor.fetchone()
    conn.close()
    return result


def get_all_clients():
    """Возвращает список всех клиентов, отсортированных по активности."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, first_seen, message_count FROM users ORDER BY message_count DESC")
    result = cursor.fetchall()
    conn.close()
    return result


def save_task(user_id, prompt, code):
    """Сохраняет новую задачу со статусом 'pending' и возвращает её id."""
    conn = get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute(
        "INSERT INTO tasks (user_id, prompt, code, status, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, prompt, code, "pending", now)
    )
    conn.commit()
    task_id = cursor.lastrowid
    conn.close()
    return task_id


def update_task(task_id, status, error=None, attempts=1):
    """Обновляет статус задачи после выполнения."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tasks SET status = ?, error = ?, attempts = ? WHERE id = ?",
        (status, error, attempts, task_id)
    )
    conn.commit()
    conn.close()


def get_user_tasks(user_id, limit=5):
    """Возвращает последние задачи пользователя."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, prompt, status, attempts, created_at FROM tasks WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit)
    )
    result = cursor.fetchall()
    conn.close()
    return result
