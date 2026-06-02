"""
Unit-тесты для ProductMapper.
Не требуют БД, LLM или внешних сервисов — словарь алиасов подаётся через tmp_path.
"""

import json
import pytest
from pathlib import Path

from product_assistant.ai.product_mapper import ProductMapper


# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------

ALIASES = {
    "aliases": {
        "ккм": "КАСКО КОМПАКТ МИНИМУМ",
        "ккп": "КАСКО КОМПАКТ ПЛЮС",
        "каско классика": "КАСКО КЛАССИКА",
        "классика": "КАСКО КЛАССИКА",
        "осаго": "ОСАГО",
        "обязательная автостраховка": "ОСАГО",
        "пнпс": "ПОВРЕЖДЕНИЯ НЕ ПОДТВЕРЖДЁННЫЕ СПРАВКАМИ",
        "юл": "СТРАХОВАНИЕ ЮРИДИЧЕСКИХ ЛИЦ",
        "нс": "СТРАХОВАНИЕ ОТ НЕСЧАСТНЫХ СЛУЧАЕВ",
    }
}


@pytest.fixture()
def aliases_file(tmp_path: Path) -> Path:
    path = tmp_path / "product_aliases.json"
    path.write_text(json.dumps(ALIASES, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture()
def mapper(aliases_file: Path) -> ProductMapper:
    return ProductMapper(aliases_path=aliases_file)


# ---------------------------------------------------------------------------
# Точное совпадение всего запроса
# ---------------------------------------------------------------------------

class TestExactMatch:
    def test_abbreviation_uppercase(self, mapper):
        assert mapper.normalize("ККМ") == "КАСКО КОМПАКТ МИНИМУМ"

    def test_abbreviation_lowercase(self, mapper):
        assert mapper.normalize("ккм") == "КАСКО КОМПАКТ МИНИМУМ"

    def test_abbreviation_mixed_case(self, mapper):
        assert mapper.normalize("Ккм") == "КАСКО КОМПАКТ МИНИМУМ"

    def test_multiword_alias(self, mapper):
        assert mapper.normalize("обязательная автостраховка") == "ОСАГО"

    def test_single_word_alias(self, mapper):
        assert mapper.normalize("осаго") == "ОСАГО"

    def test_with_surrounding_spaces(self, mapper):
        assert mapper.normalize("  ккп  ") == "КАСКО КОМПАКТ ПЛЮС"


# ---------------------------------------------------------------------------
# Алиас как подстрока в запросе
# ---------------------------------------------------------------------------

class TestSubstringMatch:
    def test_alias_at_start(self, mapper):
        result = mapper.normalize("ККМ — что покрывает?")
        assert "КАСКО КОМПАКТ МИНИМУМ" in result

    def test_alias_in_middle(self, mapper):
        result = mapper.normalize("Расскажи про ККМ подробнее")
        assert "КАСКО КОМПАКТ МИНИМУМ" in result

    def test_alias_at_end(self, mapper):
        result = mapper.normalize("Хочу узнать про ккп")
        assert "КАСКО КОМПАКТ ПЛЮС" in result

    def test_total_alias(self, mapper):
        result = mapper.normalize("Входит ли тотал в покрытие?")
        assert "КАСКО" in result

    def test_pnps_alias(self, mapper):
        result = mapper.normalize("Как работает ПНПС?")
        assert "ПОВРЕЖДЕНИЯ НЕ ПОДТВЕРЖДЁННЫЕ СПРАВКАМИ" in result

    def test_ul_alias(self, mapper):
        result = mapper.normalize("Страхование для ЮЛ")
        assert "СТРАХОВАНИЕ ЮРИДИЧЕСКИХ ЛИЦ" in result


# ---------------------------------------------------------------------------
# Жадный матч — длинный алиас побеждает короткий
# ---------------------------------------------------------------------------

class TestGreedyMatch:
    def test_long_alias_wins_over_short(self, mapper):
        # «каско классика» длиннее «классика» — должен выбраться длинный
        result = mapper.normalize("Расскажи про каско классика")
        assert "КАСКО КЛАССИКА" in result

    def test_short_alias_when_no_long(self, mapper):
        result = mapper.normalize("Мне нужна классика")
        assert "КАСКО КЛАССИКА" in result


# ---------------------------------------------------------------------------
# Граничные условия: нет совпадений
# ---------------------------------------------------------------------------

class TestNoMatch:
    def test_unknown_text_returned_as_is(self, mapper):
        text = "Какова франшиза по страхованию имущества?"
        assert mapper.normalize(text) == text

    def test_empty_string(self, mapper):
        assert mapper.normalize("") == ""

    def test_partial_abbreviation_no_false_positive(self, mapper):
        # «нс» не должен матчиться внутри слова «страхование»
        text = "Расскажи про страхование"
        assert mapper.normalize(text) == text


# ---------------------------------------------------------------------------
# get_product_name — прямой lookup
# ---------------------------------------------------------------------------

class TestGetProductName:
    def test_known_alias(self, mapper):
        assert mapper.get_product_name("ккм") == "КАСКО КОМПАКТ МИНИМУМ"

    def test_known_alias_uppercase(self, mapper):
        assert mapper.get_product_name("ККМ") == "КАСКО КОМПАКТ МИНИМУМ"

    def test_unknown_alias_returns_none(self, mapper):
        assert mapper.get_product_name("xyz") is None


# ---------------------------------------------------------------------------
# Перезагрузка словаря
# ---------------------------------------------------------------------------

class TestReload:
    def test_reload_picks_up_new_alias(self, aliases_file: Path, mapper: ProductMapper):
        # Добавляем новый алиас в файл
        data = json.loads(aliases_file.read_text(encoding="utf-8"))
        data["aliases"]["каско новинка"] = "КАСКО НОВИНКА"
        aliases_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        # До перезагрузки — не знает
        assert mapper.get_product_name("каско новинка") is None

        mapper.reload()

        # После перезагрузки — знает
        assert mapper.get_product_name("каско новинка") == "КАСКО НОВИНКА"
