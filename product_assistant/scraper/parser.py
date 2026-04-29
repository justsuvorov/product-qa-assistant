"""
Парсер сайта продуктов с поддержкой JavaScript-рендеринга (Playwright).

Логика:
1. Берём список URL продуктов из sitemap.xml (или из PRODUCT_PATHS в конфиге).
2. Для каждого URL открываем страницу в headless-браузере, ждём загрузки контента.
3. Извлекаем название (h1) и основной текст.
4. Сохраняем / обновляем записи в таблице products.

Playwright нужен, если сайт — SPA (React/Vue/Next.js и т.п.).
Установка браузера: playwright install chromium
"""

import logging
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Явный список путей продуктов относительно base_url.
# Заполняется автоматически из sitemap, но можно задать вручную.
VSK_AVTO_PATHS = [
    "/klientam/avto/kasko",
    "/klientam/avto/kasko-kompakt-minimum",
    "/klientam/avto/osago",
    "/klientam/avto/zelenaya-karta",
]


class ProductScraper:
    def __init__(self, base_url: str, timeout: int = 30, product_paths: list[str] | None = None):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        # Явные пути имеют приоритет; иначе берём из sitemap
        self._product_paths = product_paths

    def scrape_all(self) -> list[dict]:
        if not self._base_url:
            logger.warning("PRODUCTS_WEBSITE_URL не задан — парсинг пропущен")
            return []

        urls = self._resolve_product_urls()
        if not urls:
            logger.warning("Список URL продуктов пуст")
            return []

        results = []
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error(
                "Playwright не установлен. Выполните: pip install playwright && playwright install chromium"
            )
            return []

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({"Accept-Language": "ru-RU,ru;q=0.9"})

            for url in urls:
                try:
                    data = self._parse_page(page, url)
                    if data:
                        results.append(data)
                        logger.info("Спарсен продукт: %s", data["name"])
                except Exception as exc:
                    logger.warning("Не удалось спарсить %s: %s", url, exc)

            browser.close()

        logger.info("Итого спарсено продуктов: %d", len(results))
        return results

    # ------------------------------------------------------------------

    def _resolve_product_urls(self) -> list[str]:
        """Возвращает полные URL продуктов."""
        if self._product_paths:
            return [self._base_url + p for p in self._product_paths]

        # Пробуем взять из sitemap
        try:
            sitemap_urls = self._parse_sitemap()
            if sitemap_urls:
                return sitemap_urls
        except Exception as exc:
            logger.warning("Не удалось получить sitemap: %s", exc)

        # Фолбэк: сам base_url
        return [self._base_url]

    def _parse_sitemap(self) -> list[str]:
        """Парсит sitemap.xml и возвращает URL из нужного раздела."""
        import requests as req
        sitemap_url = self._base_url + "/sitemap.xml"
        resp = req.get(sitemap_url, timeout=10, headers={"User-Agent": "ProductQABot/1.0"})
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "xml")
        base_path = urlparse(self._base_url).path.rstrip("/")

        urls = []
        for loc in soup.find_all("loc"):
            url = loc.get_text(strip=True)
            parsed = urlparse(url)
            # Берём только URL того же домена и того же раздела
            if parsed.netloc == urlparse(self._base_url).netloc:
                if base_path and parsed.path.startswith(base_path):
                    urls.append(url)
        return urls

    def _parse_page(self, page, url: str) -> dict | None:
        """
        Открывает страницу через Playwright, ждёт загрузки и извлекает контент.
        """
        page.goto(url, wait_until="networkidle", timeout=self._timeout * 1000)

        # Ждём появления h1 — признак завершения рендеринга
        try:
            page.wait_for_selector("h1", timeout=10_000)
        except Exception:
            pass

        html = page.content()
        soup = BeautifulSoup(html, "lxml")

        # Название
        h1 = soup.find("h1")
        name = h1.get_text(strip=True) if h1 else urlparse(url).path.strip("/").split("/")[-1]

        # Убираем ненужные блоки
        for tag in soup.find_all(["nav", "header", "footer", "script", "style", "noscript"]):
            tag.decompose()

        # Основной контент
        content_tag = (
            soup.find("main")
            or soup.find("article")
            or soup.find("div", class_=re.compile(r"content|product|page|container", re.I))
            or soup.body
        )

        if not content_tag:
            return None

        text = content_tag.get_text(separator="\n", strip=True)
        text = re.sub(r'\n{3,}', '\n\n', text)

        if len(text) < 100:
            logger.debug("Слишком мало текста на %s (%d символов)", url, len(text))
            return None

        return {"name": name, "url": url, "content": text}
