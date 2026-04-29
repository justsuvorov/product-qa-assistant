"""
Автоматическое определение типа парсера для сайта.

Логика:
1. Делаем обычный HTTP-запрос (как requests-парсер).
2. Анализируем ответ — ищем признаки SPA/JS-рендеринга.
3. Возвращаем "playwright" или "requests".
"""

import re

import requests
from bs4 import BeautifulSoup
from loguru import logger

# Минимальный объём значимого текста, при котором считаем сайт статическим
_MIN_TEXT_LENGTH = 300

# Признаки SPA/JS-рендеринга
_SPA_PATTERNS = [
    # React
    {"tag": "div", "attrs": {"id": "root"}},
    {"tag": "div", "attrs": {"id": "__react-root"}},
    # Vue
    {"tag": "div", "attrs": {"id": "app"}},
    # Next.js
    {"tag": "div", "attrs": {"id": "__next"}},
    {"tag": "meta", "attrs": {"name": "next-head-count"}},
    # Nuxt
    {"tag": "div", "attrs": {"id": "__nuxt"}},
]

_BUNDLE_SCRIPT_RE = re.compile(
    r'(chunk|bundle|main|app|runtime)\.[a-f0-9]+\.js', re.I
)


def detect_scraper_type(url: str, timeout: int = 10) -> str:
    """
    Определяет нужный тип парсера для указанного URL.
    Возвращает "requests" или "playwright".
    """
    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ProductQABot/1.0)"},
        )
        response.raise_for_status()
    except Exception as exc:
        logger.warning("Detector: не удалось получить {}: {} — используем playwright", url, exc)
        return "playwright"

    soup = BeautifulSoup(response.text, "lxml")

    # 1. Известные SPA-маркеры в разметке
    for pattern in _SPA_PATTERNS:
        if soup.find(pattern["tag"], attrs=pattern["attrs"]):
            marker = f"{pattern['tag']}#{pattern['attrs']}"
            logger.info("Detector: найден SPA-маркер {} → playwright", marker)
            return "playwright"

    # 2. Webpack/Vite bundle-скрипты (chunked JS — признак SPA)
    for script in soup.find_all("script", src=True):
        if _BUNDLE_SCRIPT_RE.search(script["src"]):
            logger.info("Detector: найден bundle-скрипт {} → playwright", script["src"])
            return "playwright"

    # 3. Мало значимого текста — контент рендерится JS
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r'\s+', ' ', text)
    if len(text) < _MIN_TEXT_LENGTH:
        logger.info(
            "Detector: слишком мало текста ({} символов) → playwright", len(text)
        )
        return "playwright"

    logger.info("Detector: сайт статический ({} символов текста) → requests", len(text))
    return "requests"
