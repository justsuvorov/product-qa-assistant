"""
Парсер локальных документов: читает все PDF, DOCX, PPTX из указанной директории.
Не требует браузера и интернета.

Использование:
    SCRAPER_TYPE=local_files
    LOCAL_FILES_DIR=/path/to/documents
"""

from pathlib import Path

from loguru import logger

from product_assistant.scraper.base import BaseScraper
from product_assistant.scraper.document_parser import SUPPORTED_EXTENSIONS, _get_extension


class LocalFilesScraper(BaseScraper):

    def __init__(self, base_url: str = "", product_paths: list[str] | None = None,
                 timeout: int = 30, local_files_dir: str = ""):
        super().__init__(base_url=base_url, product_paths=product_paths, timeout=timeout)
        self._dir = Path(local_files_dir) if local_files_dir else None

    def scrape_all(self) -> list[dict]:
        if not self._dir:
            logger.error("LOCAL_FILES_DIR не задан")
            return []

        if not self._dir.exists():
            logger.error("Директория не найдена: {}", self._dir)
            return []

        files = [
            f for f in self._dir.rglob("*")
            if f.is_file() and _get_extension(f.name) in SUPPORTED_EXTENSIONS
        ]

        if not files:
            logger.warning("В директории {} нет поддерживаемых файлов (PDF, DOCX, PPTX)", self._dir)
            return []

        logger.info("Найдено {} файлов в {}", len(files), self._dir)

        results = []
        for f in files:
            rel_path = f.relative_to(self._dir)
            if len(rel_path.parts) > 1:
                product_name = rel_path.parts[0]
            else:
                product_name = f.stem

            try:
                text = self._extract(f)
                if text:
                    results.append({
                        "name": product_name,
                        "url": f.resolve().as_uri(),
                        "content": text,
                    })
                    logger.info("Прочитан файл: {} (продукт: {})", f.name, product_name)
                else:
                    logger.warning("Пустой контент: {}", f.name)
            except Exception as exc:
                logger.warning("Ошибка при чтении {}: {}", f.name, exc)

        logger.info("Итого прочитано (local_files): {}", len(results))
        return results

    def _extract(self, path: Path) -> str | None:
        from product_assistant.scraper.document_parser import (
            _extract_pdf, _extract_docx, _extract_pptx,
        )
        content = path.read_bytes()
        ext = _get_extension(path.name)
        extractors = {
            ".pdf": _extract_pdf,
            ".docx": _extract_docx,
            ".pptx": _extract_pptx,
        }
        return extractors[ext](content, str(path))
