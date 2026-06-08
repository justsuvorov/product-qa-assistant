"""
Интерфейс парсера продуктов.
Все реализации наследуются от BaseScraper и реализуют scrape_all().
"""

from abc import ABC, abstractmethod
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from loguru import logger


class BaseScraper(ABC):
    """
    Абстрактный парсер. Возвращает список продуктов в формате:
    [{"name": str, "url": str, "content": str}, ...]
    """

    def __init__(self, base_url: str, product_paths: list[str] | None = None, timeout: int = 30):
        self._base_url = base_url.rstrip("/")
        self._product_paths = product_paths  # явные пути; None → автопоиск
        self._timeout = timeout

    @abstractmethod
    def scrape_all(self) -> list[dict]:
        """Парсит все продукты и возвращает список словарей."""

    # ------------------------------------------------------------------
    # Общие утилиты для наследников
    # ------------------------------------------------------------------

    def _resolve_product_urls(self) -> list[str]:
        """Возвращает полные URL продуктов (явные или из sitemap)."""
        if not self._base_url:
            return []

        if self._product_paths:
            # PRODUCT_PATHS — абсолютные пути от корня домена (/klientam/avto/kasko).
            # Берём только scheme+netloc, чтобы не дублировать путь из base_url.
            parsed = urlparse(self._base_url)
            domain = f"{parsed.scheme}://{parsed.netloc}"
            return [domain + p for p in self._product_paths]

        try:
            urls = self._sitemap_urls()
            if urls:
                return urls
        except Exception as exc:
            logger.warning("Не удалось получить sitemap: {}", exc)

        return [self._base_url]

    def _sitemap_urls(self) -> list[str]:
        """Забирает URL из sitemap.xml корня домена, фильтруя по base_url."""
        parsed_base = urlparse(self._base_url)
        root = f"{parsed_base.scheme}://{parsed_base.netloc}"
        base_path = parsed_base.path.rstrip("/")
        base_netloc = parsed_base.netloc
        return self._fetch_sitemap(root + "/sitemap.xml", base_netloc, base_path)

    def _fetch_sitemap(self, sitemap_url: str, base_netloc: str, base_path: str) -> list[str]:
        """Загружает sitemap, рекурсивно обходя sitemap index."""
        resp = requests.get(sitemap_url, timeout=10, headers={"User-Agent": "ProductQABot/1.0"})
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "xml")

        # Sitemap index — рекурсивно обходим вложенные карты
        nested = soup.find_all("sitemap")
        if nested:
            urls = []
            for entry in nested:
                loc = entry.find("loc")
                if not loc:
                    continue
                try:
                    urls.extend(self._fetch_sitemap(loc.get_text(strip=True), base_netloc, base_path))
                except Exception as exc:
                    logger.warning("Не удалось получить вложенный sitemap {}: {}", loc.get_text(strip=True), exc)
            return urls

        # Обычный sitemap — фильтруем по base_path
        # Сравниваем netloc без www. (sitemap может использовать другой вариант)
        norm_base = base_netloc.removeprefix("www.")
        urls = []
        for loc in soup.find_all("loc"):
            url = loc.get_text(strip=True)
            parsed = urlparse(url)
            if parsed.netloc.removeprefix("www.") == norm_base and parsed.path.startswith(base_path):
                urls.append(url)
        return urls

    @staticmethod
    def _clean_text(text: str) -> str:
        return re.sub(r'\n{3,}', '\n\n', text).strip()
