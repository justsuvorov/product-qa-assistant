from loguru import logger
from product_assistant.ai.model import AIModel
from product_assistant.ai.postprocessor import PostProcessor
from product_assistant.ai.preprocessor import Preprocessor, ConflictMappingError
from product_assistant.reports.report_export import ReportExport


class AIAssistantService:
    def __init__(
            self,
            preprocessor: Preprocessor,
            postprocessor: PostProcessor,
            ai_model: AIModel,
            report_export: ReportExport,
    ):
        self._preprocessor = preprocessor
        self._postprocessor = postprocessor
        self._model = ai_model
        self._report_export = report_export

    def result(self) -> dict:
        try:
            # Вызываем препроцессор (здесь может возникнуть ConflictMappingError)
            prompt, product_id = self._preprocessor.query()

            # Стандартный пайплайн генерации ответа
            raw_response = self._model.response(prompt)
            formatted = self._postprocessor.report(raw_response)

            return self._report_export.response(report_text=formatted, product_id=product_id)

        except ConflictMappingError as exc:
            logger.info("Обнаружен конфликт маппинга продуктов, возвращаем варианты пользователю.")
            # Возвращаем специальный словарь-ответ для интерфейса
            return {
                "status": "conflict",
                "message": "Я нашёл упоминание нескольких продуктов. Пожалуйста, уточните, какой именно вас интересует?",
                "choices": [{"id": p.id, "name": p.name} for p in exc.products]
            }