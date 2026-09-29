"""Тесты извлечения текста из файлов."""
import sys
sys.path.insert(0, "/content/project")

from file_parser import extract_text


def test_txt_utf8():
    content = "Привет, мир!".encode("utf-8")
    text, err = extract_text(content, "test.txt")
    assert err is None
    assert text == "Привет, мир!"


def test_txt_cp1251():
    content = "Привет".encode("cp1251")
    text, err = extract_text(content, "test.txt")
    assert err is None
    assert text == "Привет"


def test_unsupported_format():
    content = b"binary"
    text, err = extract_text(content, "test.xyz")
    assert err is not None
    assert "Неподдерживаемый" in err


def test_csv_as_text():
    content = b"name,age\nAlex,30"
    text, err = extract_text(content, "test.csv")
    assert err is None
    assert "Alex" in text
