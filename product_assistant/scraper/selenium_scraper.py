"""
Парсер для SPA-сайтов на базе Selenium WebDriver.
Использует удалённый Selenium Grid (SELENIUM_URL) или локальный Chrome.

Преимущество перед Playwright: более устойчив к навигационным событиям SPA,
не теряет контекст выполнения при клиентских переходах.

Установка:
    pip install selenium
Selenium Grid (Docker):
    docker run -d -p 4444:4444 selenium/standalone-chrome
"""

import os
import re
import time
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from loguru import logger

from product_assistant.scraper.base import BaseScraper
from product_assistant.scraper.document_parser import find_document_links_from_html, extract_document_text


class SeleniumScraper(BaseScraper):

    def __init__(self, base_url: str, product_paths: list[str] | None = None,
                 timeout: int = 30, selenium_url: str = "",
                 username: str = "", password: str = ""):
        super().__init__(base_url=base_url, product_paths=product_paths, timeout=timeout)
        self._selenium_url = selenium_url
        self._username = username
        self._password = password

    def _create_driver(self):
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--lang=ru-RU")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--ignore-ssl-errors")
        options.add_argument("--allow-insecure-localhost")
        options.set_capability("acceptInsecureCerts", True)
        # Не ждём полной загрузки — используем явные ожидания элементов
        options.page_load_strategy = "none"

        if self._selenium_url:
            driver = webdriver.Remote(
                command_executor=self._selenium_url,
                options=options,
            )
        else:
            driver = webdriver.Chrome(options=options)

        driver.set_page_load_timeout(self._timeout * 4)
        return driver

    def scrape_all(self) -> list[dict]:
        if not self._base_url:
            logger.warning("PRODUCTS_WEBSITE_URL не задан — парсинг пропущен")
            return []

        driver = self._create_driver()
        results = []
        session_cookies: dict = {}

        try:
            if self._username and self._password:
                self._login(driver)
                session_cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
                logger.info("Получено {} куки сессии", len(session_cookies))

            if self._product_paths:
                urls = self._resolve_product_urls()
            else:
                urls = self._discover_urls(driver)

            for url in urls:
                try:
                    data = self._parse_page(driver, url, session_cookies=session_cookies)
                    if data:
                        results.append(data)
                        logger.info("Спарсен продукт: {}", data["name"])
                except Exception as exc:
                    logger.warning("Не удалось спарсить {}: {}", url, exc)

        finally:
            driver.quit()

        logger.info("Итого спарсено (selenium): {}", len(results))
        return results

    def _wait_for_page(self, driver):
        """Ждёт появления body и стабилизации DOM."""
        from selenium.webdriver.support.ui import WebDriverWait

        try:
            WebDriverWait(driver, self._timeout).until(
                lambda d: d.execute_script("return document.body !== null")
            )
        except Exception:
            pass

        try:
            WebDriverWait(driver, self._timeout).until(
                lambda d: d.execute_script("return document.readyState") in ("interactive", "complete")
            )
        except Exception:
            pass

        time.sleep(2)

    def _login(self, driver):
        """Авторизация через Keycloak — заполняет форму логина и сабмитит."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait

        logger.info("Выполняем авторизацию на {}", self._base_url)
        try:
            driver.get(self._base_url)
            self._wait_for_page(driver)

            # Keycloak редиректит на страницу логина — ждём поле username
            WebDriverWait(driver, self._timeout).until(
                lambda d: d.find_elements(By.ID, "username") or
                          d.find_elements(By.NAME, "username") or
                          d.find_elements(By.ID, "login")
            )

            # Заполняем логин
            for selector in [By.ID, By.NAME]:
                fields = driver.find_elements(selector, "username")
                if fields:
                    fields[0].clear()
                    fields[0].send_keys(self._username)
                    break

            # Заполняем пароль
            for selector in [By.ID, By.NAME]:
                fields = driver.find_elements(selector, "password")
                if fields:
                    fields[0].clear()
                    fields[0].send_keys(self._password)
                    break

            # Кликаем кнопку входа
            for locator in [
                (By.ID, "kc-login"),
                (By.CSS_SELECTOR, "input[type='submit']"),
                (By.CSS_SELECTOR, "button[type='submit']"),
            ]:
                btns = driver.find_elements(*locator)
                if btns:
                    btns[0].click()
                    break

            self._wait_for_page(driver)
            logger.info("Авторизация выполнена, текущий URL: {}", driver.current_url)

        except Exception as exc:
            logger.warning("Ошибка при авторизации: {}", exc)

    def _discover_urls(self, driver) -> list[str]:
        """Открывает base_url и собирает ссылки на дочерние страницы."""
        logger.info("PRODUCT_PATHS не задан — обнаруживаем продукты с {}", self._base_url)

        try:
            driver.get(self._base_url)
            self._wait_for_page(driver)

            base_parsed = urlparse(self._base_url)
            base_path = base_parsed.path.rstrip("/")

            links = driver.find_elements("tag name", "a")
            seen = set()
            urls = []

            for link in links:
                try:
                    href = link.get_attribute("href")
                    if not href:
                        continue
                    parsed = urlparse(href)
                    if parsed.netloc != base_parsed.netloc:
                        continue
                    path = parsed.path.rstrip("/")
                    if not path.startswith(base_path) or path == base_path:
                        continue
                    extra = path[len(base_path):]
                    if len(extra.split("/")) - 1 != 1:
                        continue
                    if path in seen:
                        continue
                    seen.add(path)
                    urls.append(href)
                except Exception:
                    continue

            if urls:
                logger.info("Обнаружено {} продуктов на {}", len(urls), self._base_url)
                return urls

        except Exception as exc:
            logger.warning("Ошибка при обнаружении URL с {}: {}", self._base_url, exc)

        logger.info("Дочерних ссылок не найдено — парсим базовый URL")
        return [self._base_url]

    def _parse_page(self, driver, url: str, session_cookies: dict | None = None) -> dict | None:
        driver.get(url)
        self._wait_for_page(driver)

        # Ждём появления h1
        try:
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.common.by import By
            WebDriverWait(driver, 10).until(
                lambda d: d.find_elements(By.TAG_NAME, "h1")
            )
        except Exception:
            pass

        html = driver.page_source
        soup = BeautifulSoup(html, "lxml")

        h1 = soup.find("h1")
        name = h1.get_text(strip=True) if h1 else urlparse(url).path.strip("/").split("/")[-1]

        # Документы из HTML (без JS-контекста)
        doc_links = find_document_links_from_html(soup, url)

        # Вкладки — ссылки с тем же pathname, другим query
        tab_links = self._find_tab_links(driver, url)

        # Основной текст
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
            tab_text = self._extract_tab_content(driver, tab["url"])
            if tab_text:
                sections.append(f"=== {tab['title']} ===\n{tab_text}")

        # Документы
        for doc in doc_links:
            logger.info("Обрабатываю {}: {}", doc["ext"].upper(), doc["url"])
            doc_text = extract_document_text(doc["url"], timeout=self._timeout, cookies=session_cookies)
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

    def _find_tab_links(self, driver, current_url: str) -> list[dict]:
        """Ищет ссылки с тем же pathname, но другими query-параметрами."""
        base_parsed = urlparse(current_url)
        seen = {base_parsed.query}
        tabs = []

        try:
            links = driver.find_elements("tag name", "a")
            for link in links:
                try:
                    href = link.get_attribute("href")
                    if not href:
                        continue
                    parsed = urlparse(href)
                    if parsed.netloc != base_parsed.netloc:
                        continue
                    if parsed.path != base_parsed.path:
                        continue
                    if not parsed.query or parsed.query in seen:
                        continue
                    seen.add(parsed.query)
                    title = link.text.strip() or href
                    tabs.append({"url": href, "title": title})
                except Exception:
                    continue
        except Exception as exc:
            logger.warning("Ошибка при поиске вкладок: {}", exc)

        return tabs

    def _extract_tab_content(self, driver, url: str) -> str | None:
        """Открывает вкладку и возвращает текст."""
        try:
            driver.get(url)
            self._wait_for_page(driver)

            html = driver.page_source
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
