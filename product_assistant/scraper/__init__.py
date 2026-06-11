from product_assistant.scraper.base import BaseScraper
from product_assistant.scraper.detector import detect_scraper_type
from product_assistant.scraper.requests_scraper import RequestsScraper
from product_assistant.scraper.playwright_scraper import PlaywrightScraper
from product_assistant.scraper.selenium_scraper import SeleniumScraper
from product_assistant.scraper.local_files_scraper import LocalFilesScraper


def create_scraper(
    scraper_type: str,
    base_url: str,
    product_paths: list[str] | None = None,
    timeout: int = 30,
    selenium_url: str = "",
    username: str = "",
    password: str = "",
    local_files_dir: str = "",
) -> BaseScraper:
    """
    Фабрика парсеров.

    scraper_type:
        "auto"       — автоопределение по структуре сайта
        "requests"   — статические сайты (requests + BeautifulSoup)
        "playwright" — SPA / JS-рендеринг (headless Chromium)
        "selenium"   — SPA через Selenium WebDriver (Grid или локальный Chrome)
    """
    if scraper_type == "auto":
        scraper_type = detect_scraper_type(base_url)

    if scraper_type == "local_files":
        return LocalFilesScraper(local_files_dir=local_files_dir)

    if scraper_type == "selenium":
        return SeleniumScraper(
            base_url=base_url,
            product_paths=product_paths,
            timeout=timeout,
            selenium_url=selenium_url,
            username=username,
            password=password,
        )

    scrapers = {
        "requests": RequestsScraper,
        "playwright": PlaywrightScraper,
    }

    cls = scrapers.get(scraper_type)
    if cls is None:
        raise ValueError(
            f"Неизвестный тип парсера: '{scraper_type}'. "
            f"Доступные: auto, selenium, {', '.join(scrapers.keys())}"
        )

    return cls(base_url=base_url, product_paths=product_paths, timeout=timeout)
