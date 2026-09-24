"""
Интеграционный тест SeleniumScraper на vsk.ru.

Требования:
    - Запущен Selenium Grid: docker run -d -p 4444:4444 --shm-size=2g selenium/standalone-chrome

Запуск:
    pytest tests/test_selenium_scraper_integration.py -v -s
"""

import pytest
from product_assistant.scraper.selenium_scraper import SeleniumScraper
from product_assistant.scraper import create_scraper

SELENIUM_URL = "http://localhost:4444"
TEST_URL = "https://www.vsk.ru/klientam/avto/kasko"
BASE_URL = "https://www.vsk.ru"


def _selenium_available() -> bool:
    import httpx
    try:
        r = httpx.get(f"{SELENIUM_URL}/wd/hub/status", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _selenium_available(),
    reason="Selenium Grid недоступен — запустите: docker run -d -p 4444:4444 --shm-size=2g selenium/standalone-chrome"
)


def test_selenium_driver_opens_vsk():
    """Selenium открывает vsk.ru и получает HTML."""
    scraper = SeleniumScraper(
        base_url=BASE_URL,
        product_paths=["/klientam/avto/kasko"],
        timeout=30,
        selenium_url=SELENIUM_URL,
    )
    driver = scraper._create_driver()
    try:
        driver.get(TEST_URL)
        scraper._wait_for_page(driver)
        html = driver.page_source
        assert len(html) > 1000, "HTML должен быть непустым"
        print(f"\nHTML получен: {len(html)} симв.")
    finally:
        driver.quit()


def test_selenium_scraper_parses_kasko():
    """Парсит страницу КАСКО на vsk.ru."""
    scraper = SeleniumScraper(
        base_url=BASE_URL,
        product_paths=["/klientam/avto/kasko"],
        timeout=30,
        selenium_url=SELENIUM_URL,
    )
    results = scraper.scrape_all()

    assert len(results) >= 1, "Должен быть спарсен хотя бы 1 продукт"
    product = results[0]
    assert product["name"], "Продукт должен иметь name"
    assert len(product["content"]) > 100, "Контент должен быть непустым"

    print(f"\nПродукт: {product['name']}")
    print(f"Контент ({len(product['content'])} симв.):\n{product['content'][:300]}...", flush=True)


def test_create_scraper_selenium_type():
    """Фабрика возвращает SeleniumScraper при type=selenium."""
    scraper = create_scraper(
        scraper_type="selenium",
        base_url=BASE_URL,
        selenium_url=SELENIUM_URL,
    )
    assert isinstance(scraper, SeleniumScraper)
