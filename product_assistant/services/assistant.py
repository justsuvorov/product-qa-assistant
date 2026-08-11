from loguru import logger

from product_assistant.ai.model import AIModel
from product_assistant.ai.postprocessor import PostProcessor
from product_assistant.ai.preprocessor import Preprocessor, _DIRECT_ANSWER_PREFIX
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
        logger.info("[1/4] Подготовка промпта...")
        prompt, fallback_prompt, product_id, context_cleared = self._preprocessor.query()

        if prompt.startswith(_DIRECT_ANSWER_PREFIX):
            # Прямой ответ без LLM
            raw = prompt[len(_DIRECT_ANSWER_PREFIX):]
            formatted = self._postprocessor.report(raw)
            logger.info("[2-3/4] Прямой ответ без LLM. Длина={} симв.", len(formatted))
        else:
            logger.info("[1/4] Промпт готов. product_id={}, длина промпта={} симв.", product_id, len(prompt))
            logger.info("[2/4] Отправка первичного запроса в модель ({})...", self._model.__class__.__name__)

            # Попытка #1: Первичный запрос (конкретный продукт)
            raw_response = self._model.response(prompt)
            logger.info("[2/4] Ответ получен. Длина={} симв.", len(raw_response))

            # Попытка #2: Проверка на нехватку информации и вызов Fallback (категория 'Общее')
            if "NOT_ENOUGH_INFO" in raw_response and fallback_prompt is not None:
                logger.info("[2/4] Ответ в продукте не найден (NOT_ENOUGH_INFO). Переключение на базу 'Общее'...")
                logger.info("[2/4] Отправка резервного запроса в модель (длина={} симв.)...", len(fallback_prompt))

                raw_response = self._model.response(fallback_prompt)
                logger.info("[2/4] Резервный ответ получен. Длина={} симв.", len(raw_response))

                # Если и в 'Общей' базе ничего не нашлось
                if "NOT_ENOUGH_INFO" in raw_response:
                    raw_response = "К сожалению, я не нашел ответа на ваш вопрос ни в информации о продукте, ни в общих правилах страхования."

            logger.info("[3/4] Форматирование ответа...")
            formatted = self._postprocessor.report(raw_response)

        logger.info("[4/4] Сохранение результата в БД...")
        result = self._report_export.response(report_text=formatted, product_id=product_id)
        result["context_cleared"] = context_cleared
        logger.info("[4/4] Готово. db_status={}", result.get("db_status"))

        return result
