"""RAG-память: embeddings и поиск по смыслу."""

import os
import json
import math
from datetime import datetime


def _get_client():
    """Ленивая инициализация клиента Gemini."""
    from ai import ai_client
    return ai_client


def embed_text(text):
    """Возвращает embedding (список чисел) для текста. Или None."""
    try:
        client = _get_client()
        response = client.models.embed_content(
            model="gemini-embedding-001",
            contents=text[:2000]
        )
        # В google-genai response.embeddings[0].values
        values = response.embeddings[0].values
        return list(values)
    except Exception as e:
        print("embed_text ошибка: " + str(e)[:200], flush=True)
        return None


def cosine_similarity(a, b):
    """Косинусная близость двух векторов (0..1)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def save_embedding(project_id, project_type, text):
    """Считает embedding и сохраняет в БД."""
    import database
    vec = embed_text(text)
    if not vec:
        return False

    conn = database.get_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute("""
        INSERT INTO project_embeddings (project_id, project_type, embedding, created_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (project_id) DO UPDATE
        SET embedding = EXCLUDED.embedding, created_at = EXCLUDED.created_at
    """, (project_id, project_type, json.dumps(vec), now))
    conn.commit()
    cursor.close()
    conn.close()
    return True


def find_similar_projects(query, top_k=3, min_score=0.5):
    """Ищет похожие проекты по текстовому запросу.

    Возвращает список (project_id, project_type, score, preview).
    """
    import database
    query_vec = embed_text(query)
    if not query_vec:
        return []

    conn = database.get_conn()
    cursor = conn.cursor()

    # Берём все embeddings (для нашего масштаба — ок)
    cursor.execute("""
        SELECT project_id, project_type, embedding
        FROM project_embeddings
    """)
    rows = cursor.fetchall()

    scored = []
    for pid, ptype, emb_json in rows:
        try:
            vec = json.loads(emb_json)
        except Exception:
            continue
        score = cosine_similarity(query_vec, vec)
        if score >= min_score:
            scored.append((pid, ptype, score))

    # Топ-K
    scored.sort(key=lambda x: -x[2])
    scored = scored[:top_k]

    # Подтягиваем ТЗ проектов для превью
    result = []
    for pid, ptype, score in scored:
        cursor.execute(
            "SELECT tz FROM projects WHERE id = %s",
            (pid,)
        )
        row = cursor.fetchone()
        tz = row[0] if row else ""
        result.append((pid, ptype, score, tz[:120]))

    cursor.close()
    conn.close()
    return result


def backfill_embeddings():
    """Пересчитывает embeddings для всех существующих проектов."""
    import database
    conn = database.get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id, ptype, tz, code FROM projects")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    done = 0
    for pid, ptype, tz, code in rows:
        text = (tz or "") + chr(10) + (code or "")[:1000]
        if save_embedding(pid, ptype, text):
            done += 1
    return done
