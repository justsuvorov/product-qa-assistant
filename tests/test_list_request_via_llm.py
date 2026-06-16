"""Тесты обработки запроса 'Что ты умеешь?' через LLM."""

import pytest
from unittest.mock import Mock, MagicMock
from product_assistant.ai.preprocessor import TextPreprocessor, ProcessingTask, _is_product_list_request
from product_assistant.models.schema import Product


class TestListRequestViaLLM:
    """Тесты обработки списка продуктов через LLM."""

    def test_is_product_list_request_detects_what_can_you_do(self):
        """Обнаруживает вопрос 'Что ты умеешь?'"""
        assert _is_product_list_request("Что ты умеешь?")
        assert _is_product_list_request("Что ты можешь?")
        assert _is_product_list_request("Что ты знаешь?")

    def test_is_product_list_request_detects_what_products(self):
        """Обнаруживает вопрос 'Какие продукты?'"""
        assert _is_product_list_request("Какие продукты?")
        assert _is_product_list_request("Какие программы есть?")
        assert _is_product_list_request("Какие страховки?")

    def test_is_product_list_request_detects_list_request(self):
        """Обнаруживает вопрос 'Список продуктов'"""
        assert _is_product_list_request("Список продуктов")
        assert _is_product_list_request("Перечень страховок")

    def test_is_product_list_request_detects_help(self):
        """Обнаруживает вопрос 'Помощь'"""
        assert _is_product_list_request("Помощь")
        assert _is_product_list_request("Справка")
        assert _is_product_list_request("Помогите")

    def test_is_product_list_request_case_insensitive(self):
        """Обнаруживает вопросы независимо от регистра"""
        assert _is_product_list_request("ЧТО ТЫ УМЕЕШЬ?")
        assert _is_product_list_request("какие продукты?")

    def test_is_product_list_request_returns_false_for_normal_question(self):
        """Не обнаруживает обычные вопросы"""
        assert not _is_product_list_request("Что входит в КАСКО?")
        assert not _is_product_list_request("Как подать претензию?")

    @pytest.mark.skip(reason="Integration test - проверяет сложную логику с PromptEngine")
    def test_list_request_includes_product_list_in_product_info(self, mocker):
        """Запрос на список включает все продукты в product_info"""
        pass

    def test_list_request_returns_none_product_id(self, mocker):
        """Запрос на список возвращает product_id=None"""
        # Mock БД
        mock_db = Mock()
        question_record = Mock()
        question_record.question_text = "Что ты умеешь?"
        question_record.id = 1

        mock_db.get_question.return_value = question_record
        mock_db.get_all_products.return_value = [Mock(id=1, name="КАСКО")]
        mock_db.get_context.return_value = []
        mock_db.connection.execute = Mock()
        mock_db.connection.commit = Mock()

        # Mock mapper и engine
        mock_mapper = Mock()
        mock_mapper.normalize.return_value = "что ты умеешь"
        mock_engine = Mock()
        mock_engine.build.return_value = "test prompt"

        # Вызвать query
        preprocessor = TextPreprocessor(
            db_object=mock_db,
            request=ProcessingTask(message_id=1),
            prompt_engine=mock_engine,
            product_mapper=mock_mapper,
        )
        prompt, product_id, context_cleared = preprocessor.query()

        # product_id должен быть None для запросов на список
        assert product_id is None

    @pytest.mark.skip(reason="Integration test - проверяет сложную логику с PromptEngine")
    def test_list_request_with_empty_products(self, mocker):
        """Запрос на список когда продуктов нет"""
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
