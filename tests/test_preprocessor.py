import pytest
from unittest.mock import MagicMock, patch
from product_assistant.ai.preprocessor import (
    _clean_text,
    _find_best_product,
    TextPreprocessor,
    ProcessingTask,
)
from product_assistant.ai.promt_builders import PromptEngine


# ---------------------------------------------------------------------------
# _clean_text
# ---------------------------------------------------------------------------

def test_clean_text_strips_whitespace():
    assert _clean_text("  hello  ") == "hello"


def test_clean_text_collapses_spaces():
    assert _clean_text("hello   world") == "hello world"


def test_clean_text_collapses_tabs_and_newlines():
    assert _clean_text("a\t\tb\n\nc") == "a b c"


def test_clean_text_empty():
    assert _clean_text("") == ""


# ---------------------------------------------------------------------------
# _find_best_product
# ---------------------------------------------------------------------------

def _make_product(name, pid=1):
    p = MagicMock()
    p.id = pid
    p.name = name
    return p


def test_find_best_product_returns_best_match():
    products = [
        _make_product("КАСКО Классика", pid=1),
        _make_product("ОСАГО Базовый", pid=2),
    ]
    result = _find_best_product("Хочу КАСКО", products)
    assert result.id == 1


def test_find_best_product_no_match_returns_none():
    products = [_make_product("КАСКО Классика")]
    result = _find_best_product("абракадабра xyz", products)
    assert result is None


def test_find_best_product_empty_list_returns_none():
    assert _find_best_product("вопрос", []) is None


def test_find_best_product_case_insensitive():
    products = [_make_product("ОСАГО базовый", pid=5)]
    result = _find_best_product("осаго", products)
    assert result.id == 5


# ---------------------------------------------------------------------------
# TextPreprocessor.query
# ---------------------------------------------------------------------------

def test_text_preprocessor_query_returns_prompt_and_product_id():
    product = _make_product("КАСКО Классика", pid=3)
    product.content = "Полное описание продукта КАСКО"

    question_record = MagicMock()
    question_record.question_text = "Что покрывает КАСКО?"

    db = MagicMock()
    db.get_question.return_value = question_record
    db.get_all_products.return_value = [product]
    db.connection.execute.return_value = None
    db.connection.commit.return_value = None

    engine = PromptEngine(role="R", template="{role}\n{product_info}\n{question}")
    task = ProcessingTask(message_id=1)
    preprocessor = TextPreprocessor(db_object=db, request=task, prompt_engine=engine)

    prompt, product_id = preprocessor.query()

    assert isinstance(prompt, str)
    assert product_id == 3
    assert "Что покрывает КАСКО?" in prompt or "каско" in prompt.lower()


def test_text_preprocessor_query_no_product_returns_none_id():
    question_record = MagicMock()
    question_record.question_text = "абракадабра вопрос"

    db = MagicMock()
    db.get_question.return_value = question_record
    db.get_all_products.return_value = []
    db.connection.execute.return_value = None
    db.connection.commit.return_value = None

    engine = PromptEngine(role="R", template="{role}\n{product_info}\n{question}")
    task = ProcessingTask(message_id=1)
    preprocessor = TextPreprocessor(db_object=db, request=task, prompt_engine=engine)

    _, product_id = preprocessor.query()
    assert product_id is None
