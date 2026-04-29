import pytest
from product_assistant.ai.promt_builders import PromptEngine


@pytest.fixture
def engine():
    return PromptEngine(
        role="Ты консультант",
        template="{role}\n\n{product_info}\n\n{question}",
    )


def test_build_returns_string(engine):
    result = engine.build(question="Что такое КАСКО?", product_info="КАСКО — страхование авто")
    assert isinstance(result, str)


def test_build_includes_all_parts(engine):
    result = engine.build(question="Мой вопрос", product_info="Описание продукта")
    assert "Ты консультант" in result
    assert "Описание продукта" in result
    assert "Мой вопрос" in result


def test_build_missing_key_raises_value_error():
    engine = PromptEngine(role="R", template="{role} {unknown_key}")
    with pytest.raises(ValueError, match="Ошибка в шаблоне промпта"):
        engine.build(question="q", product_info="p")


def test_build_empty_product_info(engine):
    result = engine.build(question="Вопрос", product_info="")
    assert "Вопрос" in result
