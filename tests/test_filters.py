"""Тесты парсинга фильтров."""
import sys
sys.path.insert(0, "/content/project")

from database import parse_filter_keywords


def test_parse_simple_keywords():
    result = parse_filter_keywords("python, бот")
    assert result["include"] == ["python", "бот"]
    assert result["exclude"] == []
    assert result["lang"] is None


def test_parse_with_exclude():
    result = parse_filter_keywords("python, -java, -php")
    assert result["include"] == ["python"]
    assert "java" in result["exclude"]
    assert "php" in result["exclude"]


def test_parse_with_lang():
    result = parse_filter_keywords("python, lang:en")
    assert result["include"] == ["python"]
    assert result["lang"] == "en"


def test_parse_mixed():
    result = parse_filter_keywords("python, бот, -java, lang:ru")
    assert result["include"] == ["python", "бот"]
    assert result["exclude"] == ["java"]
    assert result["lang"] == "ru"


def test_parse_empty():
    result = parse_filter_keywords("")
    assert result["include"] == []
    assert result["exclude"] == []
    assert result["lang"] is None
