"""
Парсер сайта продуктов.

Логика:
1. Загружаем главную страницу (PRODUCTS_WEBSITE_URL).
2. Находим ссылки на страницы отдельных продуктов.
3. Для каждой страницы продукта извлекаем название и основной текст.
4. Сохраняем / обновляем записи в таблице products.

Адаптируйте селекторы (CSS/тег) под структуру конкретного сайта.
"""

import logging
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class ProductScraper:
    def __init__(self, base_url: str, timeout: int = 15):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (compatible; ProductQABot/1.0)"
            )
        })

    def scrape_all(self) -> list[dict]:
        """
        Парсит все продукты с сайта.
        Возвращает список словарей: [{name, url, content}, ...].
        """
        if not self._base_url:
            logger.warning("PRODUCTS_WEBSITE_URL не задан — парсинг пропущен")
            return []

        try:
            product_links = self._collect_product_links()
        except Exception as exc:
            logger.error("Ошибка при получении списка продуктов: %s", exc)
            return []

        results = []
        for url in product_links:
            try:
                data = self._parse_product_page(url)
                if data:
                    results.append(data)
            except Exception as exc:
                logger.warning("Не удалось спарсить %s: %s", url, exc)

        logger.info("Спарсено продуктов: %d", len(results))
        return results

    # ------------------------------------------------------------------
    # Внутренние методы — адаптируйте под структуру конкретного сайта
    # ------------------------------------------------------------------

    def _collect_product_links(self) -> list[str]:
        """
        Собирает ссылки на страницы продуктов с главной страницы.
        Стратегия по умолчанию: берём все <a href>, принадлежащие
        тому же домену и содержащие ключевые слова.
        """
        html = self._get(self._base_url)
        soup = BeautifulSoup(html, "html.parser")

        base_domain = urlparse(self._base_url).netloc
        links = set()

        for tag in soup.find_all("a", href=True):
            href = tag["href"].strip()
            full_url = urljoin(self._base_url, href)
            parsed = urlparse(full_url)

            # Только ссылки того же домена, без якорей
            if parsed.netloc == base_domain and not parsed.fragment:
                links.add(full_url.split("?")[0])  # убираем query-параметры

        # Если не нашли дочерних страниц — считаем, что весь контент на главной
        if not links or links == {self._base_url}:
            return [self._base_url]

        return list(links)

    def _parse_product_page(self, url: str) -> dict | None:
        """
        Парсит одну страницу продукта.
        Адаптируйте селекторы под разметку вашего сайта.
        """
        html = self._get(url)
        soup = BeautifulSoup(html, "html.parser")

        # Название продукта: ищем h1, затем title
        name_tag = soup.find("h1") or soup.find("title")
        name = name_tag.get_text(strip=True) if name_tag else url

        # Основной контент: ищем <main>, <article>, или весь <body>
        content_tag = (
            soup.find("main")
            or soup.find("article")
            or soup.find("div", class_=re.compile(r"content|product|detail", re.I))
            or soup.body
        )

        if not content_tag:
            return None

        # Удаляем навигацию, футеры, скрипты
        for unwanted in content_tag.find_all(["nav", "footer", "script", "style", "header"]):
            unwanted.decompose()

        text = content_tag.get_text(separator="\n", strip=True)
        text = re.sub(r'\n{3,}', '\n\n', text)

        if len(text) < 50:
            return None

        return {"name": name, "url": url, "content": text}

    def _get(self, url: str) -> str:
        response = self._session.get(url, timeout=self._timeout)
        response.raise_for_status()
        response.encoding = response.apparent_encoding
        return response.text
