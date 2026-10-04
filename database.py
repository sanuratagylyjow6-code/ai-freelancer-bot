# database.py — работа с PostgreSQL (Supabase)
# Оставлены только 4 таблицы: users, full_projects, user_files, tasks

import psycopg2
from datetime import datetime
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

def get_conn():
    # Открывает новое соединение с PostgreSQL
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

def init_db():
    # Создаёт все 4 таблицы, если их нет
    conn = get_conn()
    cur = conn.cursor()
    # Таблица users — все, кто писал боту
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    # Таблица full_projects — сгенерированные проекты
    cur.execute('''
        CREATE TABLE IF NOT EXISTS full_projects (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            tz TEXT,
            files_json TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    # Таблица user_files — загруженные ТЗ (PDF/TXT)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS user_files (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            filename TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    # Таблица tasks — лог операций (для дебага)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            prompt TEXT,
            code TEXT,
            status TEXT DEFAULT 'done',
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()

def save_user(user_id, username):
    # Сохраняет юзера или обновляет username
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO users (user_id, username) VALUES (%s, %s)
        ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username
    ''', (user_id, username))
    conn.commit()
    cur.close()
    conn.close()

def get_user_stats(user_id):
    # Возвращает счётчик проектов юзера
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM full_projects WHERE user_id=%s', (user_id,))
    projects = cur.fetchone()[0]
    cur.close()
    conn.close()
    return {'projects': projects}

def save_task(user_id, prompt, code):
    # Пишет запись в лог операций
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('INSERT INTO tasks (user_id, prompt, code) VALUES (%s, %s, %s)', (user_id, prompt, code))
    conn.commit()
    cur.close()
    conn.close()

def get_user_tasks(user_id, limit=5):
    # Последние N задач юзера
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT id, prompt, code, created_at FROM tasks WHERE user_id=%s ORDER BY id DESC LIMIT %s', (user_id, limit))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def save_user_file(user_id, filename, content):
    # Сохраняет загруженный файл (PDF/TXT/MD)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('DELETE FROM user_files WHERE user_id=%s', (user_id,))
    cur.execute('INSERT INTO user_files (user_id, filename, content) VALUES (%s, %s, %s)', (user_id, filename, content))
    conn.commit()
    cur.close()
    conn.close()

def get_latest_user_file(user_id):
    # Последний загруженный файл юзера
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT filename, content FROM user_files WHERE user_id=%s ORDER BY id DESC LIMIT 1', (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row

def clear_user_files(user_id):
    # Удаляет все файлы юзера
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('DELETE FROM user_files WHERE user_id=%s', (user_id,))
    conn.commit()
    cur.close()
    conn.close()

def save_full_project(user_id, tz, files_json):
    # Сохраняет проект и возвращает его id
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('INSERT INTO full_projects (user_id, tz, files_json) VALUES (%s, %s, %s) RETURNING id', (user_id, tz, files_json))
    pid = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return pid

def get_user_full_projects(user_id, limit=10):
    # Список проектов юзера (без содержимого файлов)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT id, tz, created_at FROM full_projects WHERE user_id=%s ORDER BY id DESC LIMIT %s', (user_id, limit))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def get_full_project(pid, user_id):
    # Один проект по id (с проверкой владельца)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT id, tz, files_json FROM full_projects WHERE id=%s AND user_id=%s', (pid, user_id))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row

def update_full_project(pid, user_id, files_json, tz=None):
    # Обновляет содержимое проекта после /edit
    conn = get_conn()
    cur = conn.cursor()
    if tz:
        cur.execute('UPDATE full_projects SET files_json=%s, tz=%s WHERE id=%s AND user_id=%s', (files_json, tz, pid, user_id))
    else:
        cur.execute('UPDATE full_projects SET files_json=%s WHERE id=%s AND user_id=%s', (files_json, pid, user_id))
    conn.commit()
    cur.close()
    conn.close()
