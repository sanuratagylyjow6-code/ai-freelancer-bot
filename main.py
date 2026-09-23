"""Точка входа: запускает бота с бесконечным retry при сбоях сети."""

import time
import database
import handlers                       # ВАЖНО: импорт регистрирует все @bot.message_handler в bot
from core import bot


database.init_db()
print("✅ Модули загружены, бот готов")


while True:
    try:
        print("▶️ Запускаю polling...")
        bot.polling(none_stop=True, timeout=60)
    except Exception as e:
        print(f"❌ Polling упал: {e}")
        print("⏸ Ждём 5 секунд и перезапускаем...")
        time.sleep(5)
        continue
