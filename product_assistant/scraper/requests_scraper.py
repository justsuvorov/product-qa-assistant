"""
Парсер для статических сайтов (без JavaScript-рендеринга).
Использует requests + BeautifulSoup.
Подходит для сайтов, которые отдают готовый HTML при обычном HTTP-запросе.
"""

import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from loguru import logger

from product_assistant.scraper.base import BaseScraper


class RequestsScraper(BaseScraper):

    def __init__(self, base_url: str, product_paths: list[str] | None = None, timeout: int = 15):
        super().__init__(base_url, product_paths, timeout)
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; ProductQABot/1.0)"})

    def scrape_all(self) -> list[dict]:
        if not self._base_url:
            logger.warning("PRODUCTS_WEBSITE_URL не задан — парсинг пропущен")
            return []

        urls = self._resolve_product_urls()
        results = []

        for url in urls:
            try:
                data = self._parse_page(url)
                if data:
                    results.append(data)
                    logger.info("Спарсен продукт: {}", data["name"])
            except Exception as exc:
                logger.warning("Не удалось спарсить {}: {}", url, exc)

        logger.info("Итого спарсено (requests): {}", len(results))
        return results

    def _parse_page(self, url: str) -> dict | None:
        resp = self._session.get(url, timeout=self._timeout)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, "lxml")

        h1 = soup.find("h1")
        name = h1.get_text(strip=True) if h1 else urlparse(url).path.strip("/").split("/")[-1]

        for tag in soup.find_all(["nav", "header", "footer", "script", "style", "noscript"]):
            tag.decompose()

        content_tag = (
            soup.find("main")
            or soup.find("article")
            or soup.find("div", class_=re.compile(r"content|product|page|container", re.I))
            or soup.body
        )

        if not content_tag:
            return None

        text = self._clean_text(content_tag.get_text(separator="\n", strip=True))
        if len(text) < 100:
            return None

        return {"name": name, "url": url, "content": text}
