from product_assistant.ai.model import AIModel
from product_assistant.ai.postprocessor import PostProcessor
from product_assistant.ai.preprocessor import Preprocessor
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
        prompt, product_id = self._preprocessor.query()
        raw_response = self._model.response(prompt)
        formatted = self._postprocessor.report(raw_response)
        return self._report_export.response(report_text=formatted, product_id=product_id)
