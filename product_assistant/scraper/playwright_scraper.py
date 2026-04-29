"""
Парсер для SPA-сайтов с JavaScript-рендерингом (React, Vue, Next.js и т.п.).
Использует Playwright (headless Chromium).

Установка браузера (один раз):
    playwright install chromium
"""

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from loguru import logger

from product_assistant.scraper.base import BaseScraper


class PlaywrightScraper(BaseScraper):

    def scrape_all(self) -> list[dict]:
        if not self._base_url:
            logger.warning("PRODUCTS_WEBSITE_URL не задан — парсинг пропущен")
            return []

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error(
                "Playwright не установлен. "
                "Выполните: pip install playwright && playwright install chromium"
            )
            return []

        urls = self._resolve_product_urls()
        results = []

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(locale="ru-RU")
            page = ctx.new_page()

            for url in urls:
                try:
                    data = self._parse_page(page, url)
                    if data:
                        results.append(data)
                        logger.info("Спарсен продукт: %s", data["name"])
                except Exception as exc:
                    logger.warning("Не удалось спарсить %s: %s", url, exc)

            browser.close()

        logger.info("Итого спарсено (playwright): %d", len(results))
        return results

    def _parse_page(self, page, url: str) -> dict | None:
        page.goto(url, wait_until="networkidle", timeout=self._timeout * 1000)

        # Ждём появления h1 как признака завершения рендеринга
        try:
            page.wait_for_selector("h1", timeout=10_000)
        except Exception:
            pass

        html = page.content()
        soup = BeautifulSoup(html, "lxml")

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
