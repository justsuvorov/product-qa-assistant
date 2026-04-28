from google import genai
from abc import ABC, abstractmethod
from product_assistant.core.config import settings


class AIModel(ABC):
    @abstractmethod
    def response(self, query: str) -> str:
        pass


class GeminiModel(AIModel):
    def __init__(self):
        self._client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())
        self._generation_config = genai.types.GenerateContentConfig(
            temperature=settings.ai_temperature,
            top_p=0.95,
            top_k=64,
            max_output_tokens=4096,
        )

    def response(self, query: str) -> str:
        try:
            result = self._client.models.generate_content(
                model=settings.model_name,
                contents=query,
                config=self._generation_config,
            )
            if not result or not result.text:
                raise ValueError("Gemini не вернула текст")
            return result.text.strip()
        except Exception as exc:
            raise RuntimeError(f"Ошибка Gemini API: {exc}") from exc
