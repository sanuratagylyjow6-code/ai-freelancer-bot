# Используем официальный Python-образ (лёгкий вариант)
FROM python:3.11-slim

# Рабочая директория внутри контейнера
WORKDIR /app

# Переменные окружения для Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Сначала копируем ТОЛЬКО requirements — для кэширования слоёв
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Потом копируем весь код
COPY . .

# Открываем порт (документация, не обязательно)
EXPOSE 10000

# Запуск через gunicorn (как на Render)
CMD ["gunicorn", "main:app", "--bind", "0.0.0.0:10000", "--timeout", "120", "--workers", "1"]
