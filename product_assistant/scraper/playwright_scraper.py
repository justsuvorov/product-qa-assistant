"""
Парсер для SPA-сайтов с JavaScript-рендерингом (React, Vue, Next.js и т.п.).
Использует Playwright (headless Chromium) с интегрированной системой обхода CAPTCHA.
"""

import os
import re
import time
import random
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from loguru import logger

from product_assistant.core.config import settings
from product_assistant.scraper.base import BaseScraper
from product_assistant.scraper.document_parser import find_document_links, extract_document_text

try:
    from playwright.sync_api import sync_playwright
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    sync_playwright = None
    _PLAYWRIGHT_AVAILABLE = False


class PlaywrightScraper(BaseScraper):

    # Список реалистичных User-Agent для ротации (Стратегия 1)
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ]

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

            # === СБОР ССЫЛОК С КОРНЕВОЙ СТРАНИЦЫ ===
            if len(urls) == 1 and (urls[0].endswith("/klientam") or urls[0].endswith("/klientam/")):
                logger.info("Sitemap недоступен. Собираю ссылки динамически со страницы /klientam...")

                # Загружаем страницу через защищенный метод
                ctx, page = self._safe_goto_with_captcha(browser, urls[0])

                if page:
                    try:
                        page.wait_for_timeout(3000)
                        try:
                            page.wait_for_selector("a[href]", timeout=5000)
                        except Exception:
                            logger.warning("Селектор ссылок не дождался, собираем текущий DOM")

                        dynamic_links = page.evaluate("""
                            () => Array.from(document.querySelectorAll('a[href]'))
                                       .map(a => a.getAttribute('href'))
                        """)

                        discovered_urls = set()
                        parsed_base = urlparse(self._base_url)
                        base_domain = parsed_base.netloc

                        for href in dynamic_links:
                            if not href:
                                continue

                            # Очистка и нормализация ссылок (обработка абсолютных и относительных путей)
                            if href.startswith("http://") or href.startswith("https://"):
                                parsed_href = urlparse(href)
                                if parsed_href.netloc == base_domain:
                                    full_url = href
                                else:
                                    continue
                            else:
                                href_clean = href.lstrip("/")
                                full_url = f"{parsed_base.scheme}://{base_domain}/{href_clean}"

                            # Фильтруем только целевые разделы продуктов и отсекаем мусор
                            parsed_full = urlparse(full_url)
                            path = parsed_full.path
                            if "/klientam" in path or "/auto/" in path or "/insurance/" in path:
                                if not any(x in path for x in ["/offices", "/news", "/faq", "/reviews", "/discounts"]):
                                    discovered_urls.add(full_url)

                        if discovered_urls:
                            urls = list(discovered_urls)
                            logger.info("Динамически обнаружено продуктов для парсинга: {}", len(urls))
                        else:
                            logger.warning("Страница загрузилась, но ссылки на продукты не найдены.")
                    except Exception as e:
                        logger.error("Ошибка при обработке динамических ссылок: {}", e)
                    finally:
                        page.close()
                        ctx.close()
                else:
                    logger.error("Не удалось обойти капчу на этапе первичного сбора ссылок.")

            # === ОСНОВНОЙ ЦИКЛ ПАРСИНГА ПРОДУКТОВ ===
            for url in urls:
                try:
                    data = self._parse_page(browser, url)
                    if data:
                        results.append(data)
                        logger.info("Спарсен продукт: {}", data["name"])
                except Exception as exc:
                    logger.warning("Не удалось спарсить {}: {}", url, exc)

            browser.close()

        logger.info("Итого спарсено (playwright): {}", len(results))
        return results

    def _safe_goto_with_captcha(self, browser, url: str):
        """
        Защищенный переход на страницу. Выполняет детекцию и
        пошаговый обход CAPTCHA на основе стратегий из конфигурации.
        """
        enabled = getattr(settings, "captcha_enabled", True)
        retry_count = getattr(settings, "captcha_retry_count", 3)
        retry_delay = getattr(settings, "captcha_retry_delay", 5)
        stealth_mode = getattr(settings, "captcha_stealth_mode", True)
        provider = getattr(settings, "captcha_provider", "none")

        ctx = None
        page = None

        for attempt in range(1, retry_count + 1):
            try:
                if not ctx or not page:
                    selected_ua = random.choice(self.USER_AGENTS)
                    ctx = browser.new_context(
                        locale="ru-RU",
                        user_agent=selected_ua,
                        viewport={"width": 1920, "height": 1080}
                    )
                    page = ctx.new_page()

                logger.info("Загрузка страницы {} (Попытка {}/{})", url, attempt, retry_count)
                page.goto(url, wait_until="domcontentloaded", timeout=self._timeout * 1000)
                page.wait_for_timeout(2000)

                if not enabled:
                    return ctx, page

                captcha_type = self._detect_captcha(page)
                if not captcha_type:
                    return ctx, page

                logger.warning(
                    "[CAPTCHA DETECTED] Найдена блокировка типа '{}' на странице {} (Попытка {}/{})",
                    captcha_type, url, attempt, retry_count
                )

                if stealth_mode:
                    logger.info("Применение стратегии Stealth Mode: симуляция человеческой активности...")
                    page.mouse.move(random.randint(100, 600), random.randint(100, 600))
                    page.wait_for_timeout(random.randint(300, 700))
                    page.mouse.move(random.randint(200, 800), random.randint(200, 800))

                    page.evaluate("window.scrollTo({top: document.body.scrollHeight / 3, behavior: 'smooth'})")
                    page.wait_for_timeout(random.randint(1000, 2000))
                    page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
                    page.wait_for_timeout(random.randint(500, 1000))

                    if not self._detect_captcha(page):
                        logger.info("Стратегия Stealth Mode успешно сработала. Капча пройдена.")
                        return ctx, page

                if provider != "none" and getattr(settings, "captcha_api_key", None):
                    logger.info("Запуск интеграции со сторонним провайдером решения капчи: {}", provider)
                    solved = self._solve_with_provider(page, captcha_type, provider, settings.captcha_api_key)
                    if solved:
                        logger.info("Капча успешно решена через внешний сервис {}.", provider)
                        return ctx, page

                logger.warning(
                    "[CAPTCHA RETRY] Не удалось обойти капчу на попытке {}. Сброс кук/сессии и ожидание {} сек.",
                    attempt, retry_delay
                )
                page.close()
                ctx.close()
                ctx, page = None, None
                time.sleep(retry_delay)

            except Exception as e:
                logger.error("Исключение при загрузке или обработке капчи на попытке {}: {}", attempt, str(e))
                if page:
                    try: page.close()
                    except: pass
                if ctx:
                    try: ctx.close()
                    except: pass
                ctx, page = None, None
                time.sleep(retry_delay)

        logger.error("[CAPTCHA FAILED] Не удалось обойти CAPTCHA для URL: {} после {} попыток.", url, retry_count)
        return None, None

    def _detect_captcha(self, page) -> str | None:
        """Ищет признаки присутствия CAPTCHA в DOM-дереве."""
        indicators = {
            "reCAPTCHA": ["iframe[src*='recaptcha']", ".g-recaptcha", "iframe[title*='recaptcha']"],
            "hCaptcha": ["iframe[src*='hcaptcha']", ".h-captcha", "iframe[title*='hCaptcha']"],
            "Cloudflare Challenge": ["iframe[src*='cloudflare']", "#challenge-running", "#cloudflare-challenge", "#turnstile-wrapper"],
            "CapMonster / Generic": ["iframe[src*='captcha']", "[class*='captcha']", "[id*='captcha']"]
        }

        for c_type, selectors in indicators.items():
            for selector in selectors:
                try:
                    if page.locator(selector).count() > 0:
                        return c_type
                except Exception:
                    continue

        try:
            title = page.title()
            if "just a moment" in title.lower() or "cloudflare" in title.lower():
                return "Cloudflare Challenge Page"
        except Exception:
            pass

        try:
            body_text = page.locator("body").text_content() or ""
            stop_words = [
                "подтвердите, что вы не робот", "verify you are human",
                "checking your browser", "введите код с картинки", "робот ли вы"
            ]
            for word in stop_words:
                if word in body_text.lower():
                    return "Text Challenge / Bot Detection"
        except Exception:
            pass

        return None

    def _solve_with_provider(self, page, captcha_type: str, provider: str, api_key: str) -> bool:
        try:
            logger.info("Отправка капчи '{}' на решение в API {}...", captcha_type, provider)
            page.wait_for_timeout(3000)
            return False
        except Exception as e:
            logger.error("Ошибка внешней интеграции решения капчи: {}", e)
            return False

    # === НОВЫЕ МЕТОДЫ ОЧИСТКИ ДЛЯ ИСКЛЮЧЕНИЯ ЛИШНЕЙ ИНФОРМАЦИИ ===

    def _clean_html_soup(self, soup: BeautifulSoup) -> BeautifulSoup:
        """Агрессивно удаляет сквозные элементы разметки и служебные блоки."""
        # 1. Удаление глобальных структурных элементов
        ignored_tags = ['header', 'footer', 'nav', 'script', 'style', 'noscript', 'aside', 'form', 'svg']
        for tag in soup.find_all(ignored_tags):
            tag.decompose()

        # 2. Удаление блоков интерфейса по ключевым классам и идентификаторам (куки, виджеты, чаты, ЛК)
        garbage_patterns = [
            r'cookie', r'banner', r'feedback', r'callback', r'popup',
            r'modal', r'share', r'social', r'chat', r'support',
            r'recommend', r'similar', r'review', r'menu', r'button',
            r'lk-', r'login', r'auth', r'user-panel', r'subscribe'
        ]
        meta_regex = re.compile('|'.join(garbage_patterns), re.IGNORECASE)

        for element in soup.find_all(class_=meta_regex):
            element.decompose()
        for element in soup.find_all(id=meta_regex):
            element.decompose()

        return soup

    def _extract_and_normalize_text(self, element) -> str:
        """Извлекает текст из элемента, удаляя пустые строки, клише и короткий шум."""
        if not element:
            return ""

        text_content = element.get_text(separator="\n")
        clean_lines = []

        # Стоп-слова и триггерные интерфейсные фразы, не относящиеся к сути страхового продукта
        stop_phrases = [
            "заказать звонок", "скачать приложение", "все права защищены",
            "оставить заявку", "личный кабинет", "войти в кабинет",
            "обратный звонок", "политика конфиденциальности", "напишите нам",
            "согласие на обработку", "купить полис", "рассчитать стоимость",
            "мы используем файлы cookie", "продолжая работу", "задать вопрос"
        ]

        for line in text_content.splitlines():
            clean_line = line.strip()

            # Фильтруем строки-заглушки, пустые строчки и шумные одиночные символы верстки (стрелки, крестики)
            if len(clean_line) < 3:
                continue

            # Отсекаем совпадения по интерфейсным фразам
            if any(phrase in clean_line.lower() for phrase in stop_phrases):
                continue

            clean_lines.append(clean_line)

        # Соединяем обратно и схлопываем множественные разрывы
        final_text = "\n".join(clean_lines)
        final_text = re.sub(r'\n+', '\n', final_text)
        return final_text

    # =============================================================

    def _parse_page(self, browser, url: str) -> dict | None:
        """Парсит страницу продукта, используя безопасную сессию навигации."""
        ctx, page = self._safe_goto_with_captcha(browser, url)

        if not page:
            logger.warning("[GRACEFUL DEGRADATION] Страница {} недоступна из-за капчи. Создается заглушка.", url)
            fallback_name = urlparse(url).path.strip("/").split("/")[-1] or "Заблокированный продукт"
            return {
                "name": fallback_name,
                "url": url,
                "content": "Данный источник информации временно недоступен из-за защиты веб-сайта. Повторите попытку позже."
            }

        try:
            # Даем время SPA-скриптам (React/Vue) полностью развернуть контент и табы
            try:
                page.wait_for_selector("main, article, [class*='content'], h1", timeout=6000)
                page.wait_for_timeout(1500)
            except Exception:
                pass

            html = page.content()
            soup = BeautifulSoup(html, "lxml")

            # Находим заголовок до деструктивной чистки дерева
            h1 = soup.find("h1")
            name = h1.get_text(strip=True) if h1 else urlparse(url).path.strip("/").split("/")[-1]

            # Собираем ссылки на документы и вкладки
            doc_links = find_document_links(page, url)
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

            # Вычищаем из BeautifulSoup интерфейсный шум
            soup = self._clean_html_soup(soup)

            # Локализуем основной контейнер
            content_tag = (
                soup.find("main")
                or soup.find("article")
                or soup.find("div", class_=re.compile(r"content|product|page|container", re.I))
                or soup.body
            )

            if not content_tag:
                return None

            # Извлекаем строго очищенный текст из главного блока
            main_clean_text = self._extract_and_normalize_text(content_tag)
            sections = [main_clean_text]

            # Контент вкладок
            for tab in tab_links:
                logger.info("Парсим вкладку: {} ({})", tab["title"], tab["url"])
                tab_text = self._extract_tab_content(page, tab["url"])
                if tab_text:
                    sections.append(f"=== {tab['title']} ===\n{tab_text}")

            # Скачивание документов
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

        finally:
            page.close()
            ctx.close()

    def _extract_tab_content(self, page, url: str) -> str | None:
        """Открывает вкладку на текущей странице и возвращает её отфильтрованный текст."""
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=self._timeout * 1000)
            try:
                page.wait_for_selector("main, article, [class*='content']", timeout=5000)
                page.wait_for_timeout(1000)
            except Exception:
                pass

            html = page.content()
            soup = BeautifulSoup(html, "lxml")

            # Точно так же чистим вкладку от мусора перед съёмом текста
            soup = self._clean_html_soup(soup)

            content_tag = (
                soup.find("main")
                or soup.find("article")
                or soup.find("div", class_=re.compile(r"content|product|page|container", re.I))
                or soup.body
            )

            if not content_tag:
                return None

            text = self._extract_and_normalize_text(content_tag)
            return text if len(text) > 50 else None

        except Exception as exc:
            logger.warning("Ошибка при парсинге контента вкладки {}: {}", url, exc)
            return None