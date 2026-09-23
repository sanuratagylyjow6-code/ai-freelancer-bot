"""Парсинг веб-страниц (пока — на тренировочном сайте)."""

import requests
from bs4 import BeautifulSoup


def parse_quotes():
    """Собирает цитаты с quotes.toscrape.com. Возвращает список строк."""
    url = "http://quotes.toscrape.com/"
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    results = []
    for quote_div in soup.find_all("div", class_="quote"):
        text = quote_div.find("span", class_="text").get_text(strip=True)
        author = quote_div.find("small", class_="author").get_text(strip=True)
        results.append(f"{text} — {author}")

    return results
