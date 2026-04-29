import pytest
from unittest.mock import patch, MagicMock
from product_assistant.ai.model import ServiceLLMModel


class _MockModel(ServiceLLMModel):
    """Concrete implementation for testing retry logic."""

    def __init__(self):
        self.call_count = 0
        self._side_effects: list = []

    def _call_api(self, query: str) -> str:
        self.call_count += 1
        if self._side_effects:
            effect = self._side_effects.pop(0)
            if isinstance(effect, Exception):
                raise effect
        return "ok"


@patch("time.sleep", return_value=None)
def test_response_succeeds_on_first_try(mock_sleep):
    model = _MockModel()
    result = model.response("query")
    assert result == "ok"
    assert model.call_count == 1
    mock_sleep.assert_not_called()


@patch("time.sleep", return_value=None)
def test_response_retries_on_overload(mock_sleep):
    model = _MockModel()
    model._side_effects = [
        Exception("503 Service Unavailable"),
        Exception("503 Service Unavailable"),
    ]
    result = model.response("query")
    assert result == "ok"
    assert model.call_count == 3
    assert mock_sleep.call_count == 2


@patch("time.sleep", return_value=None)
def test_response_returns_overload_message_after_all_retries(mock_sleep):
    model = _MockModel()
    model._side_effects = [
        Exception("503 UNAVAILABLE"),
        Exception("503 UNAVAILABLE"),
        Exception("503 UNAVAILABLE"),
    ]
    result = model.response("query")
    assert "перегружена" in result.lower() or "повторите" in result.lower()


@patch("time.sleep", return_value=None)
def test_response_raises_on_non_overload_error(mock_sleep):
    model = _MockModel()
    model._side_effects = [RuntimeError("unexpected crash")]
    with pytest.raises(RuntimeError, match="unexpected crash"):
        model.response("query")


def test_is_overload_detects_503():
    assert ServiceLLMModel._is_overload(Exception("503 error")) is True


def test_is_overload_detects_unavailable():
    assert ServiceLLMModel._is_overload(Exception("UNAVAILABLE")) is True


def test_is_overload_detects_overloaded():
    assert ServiceLLMModel._is_overload(Exception("model is overloaded")) is True


def test_is_overload_returns_false_for_other_errors():
    assert ServiceLLMModel._is_overload(Exception("network timeout")) is False
