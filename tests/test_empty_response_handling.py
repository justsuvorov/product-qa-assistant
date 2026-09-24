"""Тесты для обработки ошибок пустого ответа от Qwen."""

import pytest
from unittest.mock import Mock, patch
from product_assistant.ai.model import QwenModel, ServiceLLMModel


class TestEmptyResponseHandling:
    """Тесты обработки ошибок пустого ответа."""

    def test_empty_response_retries_with_short_delay(self, mocker):
        """Пустой ответ → 3 retry с задержкой 1 сек."""
        mock_model = Mock(spec=ServiceLLMModel)
        mock_model.retries = 3
        mock_model.empty_response_retries = 3
        mock_model.empty_response_delay = 1

        # Первые 2 раза выбросить ошибку пустого ответа, 3-й раз вернуть сообщение
        call_count = [0]

        def side_effect(query):
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("Qwen не вернул текст")
            return "Сервис модели временно недоступен, повторите запрос позже."

        mock_model._call_api = side_effect
        mock_model._is_empty_response = ServiceLLMModel._is_empty_response
        mock_model._is_overload = ServiceLLMModel._is_overload

        mock_sleep = mocker.patch('time.sleep')

        # Вызвать response с реальной логикой
        result = ServiceLLMModel.response(mock_model, "test query")

        # Проверить что был сон с правильной задержкой
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(1)  # 1 сек, а не 5

        # Проверить что вернулось сообщение об ошибке
        assert "временно недоступен" in result

    def test_empty_response_after_max_retries_returns_message(self, mocker):
        """После 3 неудачных попыток вернуть сообщение об ошибке."""
        mock_model = Mock(spec=ServiceLLMModel)
        mock_model.retries = 3
        mock_model.empty_response_retries = 3
        mock_model.empty_response_delay = 1

        # Всегда выбросить ошибку пустого ответа
        mock_model._call_api = Mock(side_effect=ValueError("Qwen не вернул текст"))
        mock_model._is_empty_response = ServiceLLMModel._is_empty_response
        mock_model._is_overload = ServiceLLMModel._is_overload

        mocker.patch('time.sleep')

        result = ServiceLLMModel.response(mock_model, "test query")

        # Проверить что вернулось сообщение об ошибке
        assert result == "Сервис модели временно недоступен, повторите запрос позже."
        # Проверить что было 3 попытки вызвать API
        assert mock_model._call_api.call_count == 3

    def test_is_empty_response_detects_no_text(self):
        """Проверить что _is_empty_response обнаруживает ошибку 'не вернул текст'."""
        exc = ValueError("Qwen не вернул текст")
        assert ServiceLLMModel._is_empty_response(exc)

    def test_is_empty_response_detects_no_response(self):
        """Проверить что _is_empty_response обнаруживает 'no response'."""
        exc = ValueError("No response from Qwen")
        assert ServiceLLMModel._is_empty_response(exc)

    def test_is_empty_response_case_insensitive(self):
        """Проверить что проверка case-insensitive."""
        exc = ValueError("QWEN НЕ ВЕРНУЛ ТЕКСТ")
        assert ServiceLLMModel._is_empty_response(exc)

    def test_is_empty_response_returns_false_for_other_errors(self):
        """Проверить что другие ошибки не обнаруживаются как empty response."""
        exc = ValueError("Some other error")
        assert not ServiceLLMModel._is_empty_response(exc)

    def test_qwen_model_returns_error_message_on_empty_response(self, mocker):
        """Qwen модель возвращает сообщение об ошибке при пустом ответе."""
        # Mock httpx.Client
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"text": "<think>thinking</think>"}]  # После удаления think — пусто
        }

        mock_client = Mock()
        mock_client.post.return_value = mock_response

        mocker.patch('product_assistant.ai.model.httpx.Client', return_value=mock_client)
        mocker.patch('product_assistant.ai.model.settings')
        mocker.patch('time.sleep')

        model = QwenModel()
        result = model.response("test query")

        # Должно вернуться сообщение об ошибке
        assert "временно недоступен" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
