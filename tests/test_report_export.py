import pytest
from unittest.mock import MagicMock
from product_assistant.reports.report_export import ReportExport
from product_assistant.ai.preprocessor import ProcessingTask


@pytest.fixture
def export():
    db = MagicMock()
    task = ProcessingTask(message_id=42)
    return ReportExport(db_object=db, processing_task=task)


def test_response_returns_correct_structure(export):
    result = export.response("Ответ на вопрос", product_id=7)
    assert result["message_id"] == 42
    assert result["status"] == "success"
    assert result["db_status"] == "saved"
    assert result["payload"]["text"] == "Ответ на вопрос"
    assert result["payload"]["format"] == "telegram_markdown"


def test_response_calls_update_result(export):
    export.response("Текст", product_id=3)
    export._db.update_result.assert_called_once_with(
        message_id=42, result_text="Текст", product_id=3
    )


def test_response_with_no_product_id(export):
    result = export.response("Ответ", product_id=None)
    assert result["db_status"] == "saved"


def test_response_db_error_captured(export):
    export._db.update_result.side_effect = RuntimeError("connection lost")
    result = export.response("Ответ")
    assert result["db_status"].startswith("error:")
    assert result["status"] == "success"
