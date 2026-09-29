"""Извлечение текста из документов."""

import os
import io


def extract_text(file_bytes, filename):
    """Возвращает (text, error). Поддерживает TXT, MD, CSV, PDF."""
    name_lower = filename.lower()

    # Простые текстовые форматы
    if name_lower.endswith((".txt", ".md", ".csv", ".json", ".py")):
        try:
            for enc in ("utf-8", "cp1251", "latin-1"):
                try:
                    return file_bytes.decode(enc), None
                except UnicodeDecodeError:
                    continue
            return None, "Не удалось определить кодировку"
        except Exception as e:
            return None, str(e)

    # PDF через pypdf
    if name_lower.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(file_bytes))
            pages_text = []
            for page in reader.pages[:30]:  # максимум 30 страниц
                pages_text.append(page.extract_text() or "")
            text = "\n".join(pages_text).strip()
            if not text:
                return None, "PDF пустой или без текстового слоя (возможно, скан)"
            return text[:15000], None
        except ImportError:
            return None, "Не установлена библиотека pypdf"
        except Exception as e:
            return None, "Ошибка чтения PDF: " + str(e)

    return None, "Неподдерживаемый формат. Поддерживаются: TXT, MD, CSV, JSON, PDF"
