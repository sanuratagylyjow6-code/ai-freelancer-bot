"""Тесты парсеров Telegram-каналов."""
import sys
sys.path.insert(0, "/content/project")

from jobs import _parse_allgigs, _parse_kwork_rss


def test_parse_allgigs_simple():
    raw = """📌
Разработка
Python-разработчик
в компанию X для проекта Y
Бэкенд-разработчик
для создания API
🔖
Оцените подборку
"""
    jobs = _parse_allgigs(raw, "test_prefix")
    assert len(jobs) >= 2
    assert jobs[0]["category"] == "Разработка"
    assert "Python" in jobs[0]["title"]


def test_parse_allgigs_empty():
    jobs = _parse_allgigs("", "test")
    assert jobs == []


def test_parse_kwork_title():
    items = [
        ("guid1", "Сделаю бота за 5000 руб.", "https://kwork.ru/1", "desc", "2026-01-01")
    ]
    jobs = _parse_kwork_rss(items)
    assert len(jobs) == 1
    assert "5000" in jobs[0]["description"] or "5000" in jobs[0]["title"]
    assert jobs[0]["channel"] == "kwork"
