from product_assistant.scraper.base import BaseScraper
from product_assistant.scraper.requests_scraper import RequestsScraper
from product_assistant.scraper.playwright_scraper import PlaywrightScraper


def create_scraper(
    scraper_type: str,
    base_url: str,
    product_paths: list[str] | None = None,
    timeout: int = 30,
) -> BaseScraper:
    """
    Фабрика парсеров.

    scraper_type:
        "requests"   — статические сайты (requests + BeautifulSoup)
        "playwright" — SPA / JS-рендеринг (headless Chromium)
    """
    scrapers = {
        "requests": RequestsScraper,
        "playwright": PlaywrightScraper,
    }

    cls = scrapers.get(scraper_type)
    if cls is None:
        raise ValueError(
            f"Неизвестный тип парсера: '{scraper_type}'. "
            f"Доступные: {list(scrapers.keys())}"
        )

    return cls(base_url=base_url, product_paths=product_paths, timeout=timeout)
