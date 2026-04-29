import pytest
from product_assistant.ai.postprocessor import PostProcessor


@pytest.fixture
def processor():
    return PostProcessor()


def test_report_empty_string(processor):
    assert processor.report("") == ""


def test_report_removes_code_blocks(processor):
    raw = "```python\nsome code\n```"
    result = processor.report(raw)
    assert "```" not in result


def test_report_removes_intro_phrase_vot(processor):
    raw = "Вот ответ:\nПокрытие включено."
    result = processor.report(raw)
    assert not result.startswith("Вот")


def test_report_removes_intro_phrase_konechno(processor):
    raw = "Конечно, помогу вам.\nДа, покрытие есть."
    result = processor.report(raw)
    assert not result.startswith("Конечно")


def test_report_normalizes_excess_newlines(processor):
    raw = "Строка 1\n\n\n\n\nСтрока 2"
    result = processor.report(raw)
    assert "\n\n\n" not in result


def test_report_strips_outer_quotes(processor):
    raw = '"Ответ без кавычек"'
    result = processor.report(raw)
    assert not result.startswith('"')
    assert not result.endswith('"')


def test_escape_underscores(processor):
    result = processor._escape_for_markdown_v2("some_word")
    assert r"\_" in result


def test_escape_square_brackets(processor):
    result = processor._escape_for_markdown_v2("see [here]")
    assert r"\[" in result
    assert r"\]" in result


def test_escape_parentheses(processor):
    result = processor._escape_for_markdown_v2("(value)")
    assert r"\(" in result
    assert r"\)" in result


def test_double_asterisk_preserved(processor):
    result = processor._escape_for_markdown_v2("**bold**")
    assert "**" in result


def test_single_asterisk_escaped(processor):
    result = processor._escape_for_markdown_v2("a * b")
    assert r"\*" in result


def test_digit_dot_escaped(processor):
    result = processor._escape_for_markdown_v2("1. item")
    assert r"1\." in result
