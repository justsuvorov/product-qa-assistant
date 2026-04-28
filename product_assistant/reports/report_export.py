from product_assistant.ai.preprocessor import ProcessingTask
from product_assistant.models.schema import DBObject


class ReportExport:
    def __init__(self, db_object: DBObject, processing_task: ProcessingTask):
        self._db = db_object
        self._task = processing_task

    def response(self, report_text: str, product_id: int | None = None) -> dict:
        message_id = self._task.message_id
        try:
            self._db.update_result(
                message_id=message_id,
                result_text=report_text,
                product_id=product_id,
            )
            db_status = "saved"
        except Exception as exc:
            db_status = f"error: {exc}"

        return {
            "message_id": message_id,
            "status": "success",
            "db_status": db_status,
            "payload": {
                "text": report_text,
                "format": "telegram_markdown",
            },
        }
