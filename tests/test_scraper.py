import pytest
from unittest.mock import patch, MagicMock
from product_assistant.scraper.base import BaseScraper
from product_assistant.scraper import create_scraper


# ---------------------------------------------------------------------------
# BaseScraper._clean_text
# ---------------------------------------------------------------------------

def test_clean_text_collapses_newlines():
    result = BaseScraper._clean_text("a\n\n\n\nb")
    assert "\n\n\n" not in result
    assert "a" in result
    assert "b" in result


def test_clean_text_strips():
    result = BaseScraper._clean_text("  text  ")
    assert result == "text"


# ---------------------------------------------------------------------------
# BaseScraper._resolve_product_urls with explicit paths
# ---------------------------------------------------------------------------

class _ConcreteScaper(BaseScraper):
    def scrape_all(self):
        return []


def test_resolve_product_urls_explicit_paths():
    scraper = _ConcreteScaper(
        base_url="https://example.com/products",
        product_paths=["/avto/kasko", "/avto/osago"],
    )
    urls = scraper._resolve_product_urls()
    assert urls == [
        "https://example.com/avto/kasko",
        "https://example.com/avto/osago",
    ]


def test_resolve_product_urls_empty_base_url():
    scraper = _ConcreteScaper(base_url="", product_paths=None)
    assert scraper._resolve_product_urls() == []


def test_resolve_product_urls_falls_back_to_base_url_when_no_sitemap():
    scraper = _ConcreteScaper(
        base_url="https://example.com",
        product_paths=None,
    )
    with patch.object(scraper, "_sitemap_urls", side_effect=Exception("timeout")):
        urls = scraper._resolve_product_urls()
    assert urls == ["https://example.com"]


# ---------------------------------------------------------------------------
# create_scraper factory
# ---------------------------------------------------------------------------

def test_create_scraper_requests():
    scraper = create_scraper("requests", "https://example.com")
    from product_assistant.scraper.requests_scraper import RequestsScraper
    assert isinstance(scraper, RequestsScraper)


def test_create_scraper_playwright():
    scraper = create_scraper("playwright", "https://example.com")
    from product_assistant.scraper.playwright_scraper import PlaywrightScraper
    assert isinstance(scraper, PlaywrightScraper)


def test_create_scraper_invalid_type():
    with pytest.raises(ValueError, match="Неизвестный тип парсера"):
        create_scraper("unknown_type", "https://example.com")


def test_create_scraper_auto_delegates_to_detector():
    with patch(
        "product_assistant.scraper.detect_scraper_type", return_value="requests"
    ) as mock_detect:
        scraper = create_scraper("auto", "https://example.com")
        mock_detect.assert_called_once_with("https://example.com")
        from product_assistant.scraper.requests_scraper import RequestsScraper
        assert isinstance(scraper, RequestsScraper)
