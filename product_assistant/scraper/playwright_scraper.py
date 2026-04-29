"""
Парсер для SPA-сайтов с JavaScript-рендерингом (React, Vue, Next.js и т.п.).
Использует Playwright (headless Chromium).

Установка браузера (один раз):
    playwright install chromium
"""

import os
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from loguru import logger

from product_assistant.scraper.base import BaseScraper
from product_assistant.scraper.document_parser import find_document_links, extract_document_text

try:
    from playwright.sync_api import sync_playwright
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    sync_playwright = None
    _PLAYWRIGHT_AVAILABLE = False


class PlaywrightScraper(BaseScraper):

    def scrape_all(self) -> list[dict]:
        if not self._base_url:
            logger.warning("PRODUCTS_WEBSITE_URL не задан — парсинг пропущен")
            return []

        if not _PLAYWRIGHT_AVAILABLE:
            logger.error(
                "Playwright не установлен. "
                "Выполните: pip install playwright && playwright install chromium"
            )
            return []

        urls = self._resolve_product_urls()
        results = []

        proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
        proxy = {"server": proxy_url} if proxy_url else None

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, proxy=proxy)
            ctx = browser.new_context(locale="ru-RU")
            page = ctx.new_page()

            for url in urls:
                try:
                    data = self._parse_page(page, url)
                    if data:
                        results.append(data)
                        logger.info("Спарсен продукт: {}", data["name"])
                except Exception as exc:
                    logger.warning("Не удалось спарсить {}: {}", url, exc)

            browser.close()

        logger.info("Итого спарсено (playwright): {}", len(results))
        return results

    def _parse_page(self, page, url: str) -> dict | None:
        page.goto(url, wait_until="load", timeout=self._timeout * 1000)

        try:
            page.wait_for_selector("h1", timeout=10_000)
        except Exception:
            pass

        html = page.content()
        soup = BeautifulSoup(html, "lxml")

        h1 = soup.find("h1")
        name = h1.get_text(strip=True) if h1 else urlparse(url).path.strip("/").split("/")[-1]

        # Документы (PDF, DOCX, PPTX) — через JS для корректного URL
        doc_links = find_document_links(page, url)

        # Вкладки/виджеты: ссылки с тем же pathname, но другими query-параметрами
        tab_links = page.evaluate("""
            (currentUrl) => {
                const base = new URL(currentUrl);
                const seen = new Set([base.search]);
                return Array.from(document.querySelectorAll('a[href]'))
                    .map(a => {
                        try {
                            const u = new URL(a.href);
                            return { url: a.href, title: a.textContent.trim() || a.href, search: u.search };
                        } catch { return null; }
                    })
                    .filter(item => {
                        if (!item) return false;
                        const u = new URL(item.url);
                        if (u.pathname !== base.pathname) return false;
                        if (!u.search || seen.has(u.search)) return false;
                        seen.add(u.search);
                        return true;
                    });
            }
        """, url)

        # Основной текст страницы
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

        sections = [self._clean_text(content_tag.get_text(separator="\n", strip=True))]

        # Контент вкладок
        for tab in tab_links:
            logger.info("Парсим вкладку: {} ({})", tab["title"], tab["url"])
            tab_text = self._extract_tab_content(page, tab["url"])
            if tab_text:
                sections.append(f"=== {tab['title']} ===\n{tab_text}")

        # Документы (PDF / DOCX / PPTX)
        for doc in doc_links:
            logger.info("Обрабатываю {} ({}): {}", doc["ext"].upper(), doc["title"], doc["url"])
            doc_text = extract_document_text(doc["url"], timeout=self._timeout)
            if doc_text:
                sections.append(f"--- Документ [{doc['ext'].upper()}]: {doc['title']} ---\n{doc_text}")

        if doc_links:
            logger.info("Документов на странице {}: {}", url, len(doc_links))
        if tab_links:
            logger.info("Вкладок на странице {}: {}", url, len(tab_links))

        full_content = "\n\n".join(s for s in sections if s)

        if len(full_content) < 100:
            return None

        return {"name": name, "url": url, "content": full_content}

    def _extract_tab_content(self, page, url: str) -> str | None:
        """Открывает вкладку по URL и возвращает её текст."""
        try:
            page.goto(url, wait_until="load", timeout=self._timeout * 1000)
            # Ждём появления контента вкладки
            try:
                page.wait_for_selector("main, article, [class*='content']", timeout=8_000)
            except Exception:
                pass

            html = page.content()
            soup = BeautifulSoup(html, "lxml")

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
            return text if len(text) > 50 else None

        except Exception as exc:
            logger.warning("Ошибка при парсинге вкладки {}: {}", url, exc)
            return None
