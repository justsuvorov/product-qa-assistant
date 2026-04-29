"""
Утилита для извлечения текста из PDF-документов.
Скачивает PDF по URL (через прокси если задан) и возвращает текст.
"""

import io
import os
import re
from urllib.parse import urljoin, urlparse

import httpx
from loguru import logger


def find_pdf_links(soup, page_url: str) -> list[dict]:
    """
    Ищет все PDF-ссылки в BeautifulSoup-дереве страницы.
    Возвращает список {'url': ..., 'title': ...}.
    """
    pdf_links = []
    seen = set()

    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith("mailto:") or href.startswith("javascript:"):
            continue

        # Полный URL
        full_url = urljoin(page_url, href)

        # Считаем ссылкой на PDF если путь заканчивается на .pdf
        # или href содержит .pdf (бывает с query-параметрами)
        parsed_path = urlparse(full_url).path.lower()
        if ".pdf" not in parsed_path:
            continue

        if full_url in seen:
            continue
        seen.add(full_url)

        title = tag.get_text(strip=True) or parsed_path.split("/")[-1]
        pdf_links.append({"url": full_url, "title": title})

    return pdf_links


def extract_pdf_text(pdf_url: str, timeout: int = 30) -> str | None:
    """
    Скачивает PDF и извлекает из него текст через pymupdf.
    Прокси берётся из переменных окружения HTTPS_PROXY / HTTP_PROXY.
    Возвращает текст или None при ошибке.
    """
    try:
        import pymupdf as fitz
    except ImportError:
        try:
            import fitz
        except ImportError:
            logger.error("pymupdf не установлен. Выполните: pip install pymupdf")
            return None

    proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")

    try:
        with httpx.Client(
            proxy=proxy_url,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ProductQABot/1.0)"},
            follow_redirects=True,
        ) as client:
            response = client.get(pdf_url)
            response.raise_for_status()

        pdf_bytes = io.BytesIO(response.content)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        pages_text = []
        for page in doc:
            pages_text.append(page.get_text())
        doc.close()

        text = "\n".join(pages_text)
        text = re.sub(r'\n{3,}', '\n\n', text).strip()

        if len(text) < 50:
            logger.debug("PDF слишком короткий или защищён: {}", pdf_url)
            return None

        return text

    except Exception as exc:
        logger.warning("Ошибка при обработке PDF {}: {}", pdf_url, exc)
        return None
