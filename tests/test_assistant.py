import pytest
from unittest.mock import MagicMock
from product_assistant.services.assistant import AIAssistantService


@pytest.fixture
def service():
    preprocessor = MagicMock()
    preprocessor.query.return_value = ("промпт для модели", 5)

    postprocessor = MagicMock()
    postprocessor.report.return_value = "Отформатированный ответ"

    ai_model = MagicMock()
    ai_model.response.return_value = "Сырой ответ LLM"

    report_export = MagicMock()
    report_export.response.return_value = {
        "message_id": 1,
        "status": "success",
        "db_status": "saved",
        "payload": {"text": "Отформатированный ответ", "format": "telegram_markdown"},
    }

    return AIAssistantService(
        preprocessor=preprocessor,
        postprocessor=postprocessor,
        ai_model=ai_model,
        report_export=report_export,
    )


def test_result_calls_pipeline_in_order(service):
    result = service.result()

    service._preprocessor.query.assert_called_once()
    service._model.response.assert_called_once_with("промпт для модели")
    service._postprocessor.report.assert_called_once_with("Сырой ответ LLM")
    service._report_export.response.assert_called_once_with(
        report_text="Отформатированный ответ", product_id=5
    )


def test_result_returns_export_dict(service):
    result = service.result()
    assert result["status"] == "success"
    assert result["payload"]["text"] == "Отформатированный ответ"


def test_result_passes_product_id_to_export(service):
    service._preprocessor.query.return_value = ("промпт", 99)
    service.result()
    service._report_export.response.assert_called_once_with(
        report_text="Отформатированный ответ", product_id=99
    )
