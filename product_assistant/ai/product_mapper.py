"""
ProductMapper — нормализация пользовательских запросов через словарь алиасов.

Порядок проверки:
  1. Точное совпадение всего запроса с алиасом (регистронезависимо).
  2. Поиск алиаса как подстроки внутри запроса (от длинных к коротким — жадный матч).
  3. Если ни один алиас не найден — возвращает исходный текст без изменений.

При нескольких совпадениях используется наиболее длинный (специфичный) алиас.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from loguru import logger


class ProductMapper:
    """
    Загружает словарь алиасов из JSON-файла и нормализует входной текст.

    JSON-формат::

        {
          "aliases": {
            "ккм": "КАСКО КОМПАКТ МИНИМУМ",
            "ккп": "КАСКО КОМПАКТ ПЛЮС",
            ...
          }
        }

    Добавление нового синонима — только правка JSON, без изменения кода.
    """

    def __init__(self, aliases_path: str | Path | None = None) -> None:
        if aliases_path is None:
            aliases_path = Path(__file__).parent.parent.parent / "product_aliases.json"
        self._path = Path(aliases_path)
        self._aliases: dict[str, str] = self._load(self._path)
        # Сортируем по убыванию длины ключа — длинные алиасы матчатся первыми
        self._sorted_keys: list[str] = sorted(self._aliases, key=len, reverse=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def normalize(self, text: str) -> str:
        """
        Возвращает текст с подставленным product name вместо алиаса.

        Если совпадений нет — возвращает исходный ``text`` без изменений.
        Если несколько алиасов подходят — использует наиболее длинный.
        """
        lower = text.lower().strip()

        # 1. Точное совпадение всего запроса
        if lower in self._aliases:
            product_name = self._aliases[lower]
            logger.debug(
                "ProductMapper | exact match | input='{}' alias='{}' product='{}'",
                text, lower, product_name,
            )
            return product_name

        # 2. Поиск алиаса как подстроки (жадный — от длинных к коротким)
        found_alias: str | None = None
        found_product: str | None = None

        for alias in self._sorted_keys:
            # Матчим по границам слов, чтобы «нс» не срабатывал внутри «страхование»
            pattern = r'(?<!\w)' + re.escape(alias) + r'(?!\w)'
            if re.search(pattern, lower):
                found_alias = alias
                found_product = self._aliases[alias]
                break  # берём первый (самый длинный) совпавший алиас

        if found_alias and found_product:
            # Подставляем product name вместо найденного алиаса в оригинальном тексте
            pattern = r'(?<!\w)' + re.escape(found_alias) + r'(?!\w)'
            normalized = re.sub(pattern, found_product, lower, flags=re.IGNORECASE)
            logger.debug(
                "ProductMapper | substring match | input='{}' alias='{}' product='{}' normalized='{}'",
                text, found_alias, found_product, normalized,
            )
            return normalized

        # 3. Совпадений нет
        logger.debug("ProductMapper | no match | input='{}'", text)
        return text

    def get_product_name(self, alias: str) -> str | None:
        """Прямой поиск product name по точному алиасу (регистронезависимо)."""
        return self._aliases.get(alias.lower().strip())

    def reload(self) -> None:
        """Перезагружает словарь из файла без перезапуска приложения."""
        self._aliases = self._load(self._path)
        self._sorted_keys = sorted(self._aliases, key=len, reverse=True)
        logger.info("ProductMapper | aliases reloaded from '{}'", self._path)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    @staticmethod
    def _load(path: Path) -> dict[str, str]:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        aliases: dict[str, str] = {
            k.lower().strip(): v
            for k, v in data.get("aliases", {}).items()
        }
        logger.info("ProductMapper | loaded {} aliases from '{}'", len(aliases), path)
        return aliases
