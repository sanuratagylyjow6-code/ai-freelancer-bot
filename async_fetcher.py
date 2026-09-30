"""Асинхронный сбор вакансий из всех источников."""

import asyncio
import aiohttp
import time
from datetime import datetime


async def fetch_url(session, url, timeout=15):
    """Асинхронно скачивает URL. Возвращает (url, text, error)."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            text = await resp.text()
            return (url, text, None)
    except Exception as e:
        return (url, None, str(e))


async def fetch_tg_channels(channels, max_posts=3):
    """Асинхронно скачивает N Telegram-каналов параллельно."""
    from bs4 import BeautifulSoup

    urls = ["https://t.me/s/" + ch for ch in channels]
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
        tasks = [fetch_url(session, url) for url in urls]
        results = await asyncio.gather(*tasks)

    parsed = {}
    for (url, text, err), ch in zip(results, channels):
        if err or not text:
            parsed[ch] = []
            continue
        soup = BeautifulSoup(text, "html.parser")
        posts = soup.find_all("div", class_="tgme_widget_message")
        parsed[ch] = posts[-max_posts:]
    return parsed


async def fetch_rss_feeds(sources):
    """Асинхронно скачивает N RSS-фидов параллельно.

    sources: список (url, parser_type)
    Возвращает dict {parser_type: xml_text}
    """
    urls = [s[0] for s in sources]
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
        tasks = [fetch_url(session, url, timeout=20) for url in urls]
        results = await asyncio.gather(*tasks)

    out = {}
    for (url, text, err), (u, ptype) in zip(results, sources):
        if err or not text:
            out[ptype] = None
        else:
            out[ptype] = text
    return out


def run_async(coro):
    """Запускает корутину в новом event loop (для использования в sync-коде)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Если loop уже запущен — создаём новый в отдельном потоке
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)
