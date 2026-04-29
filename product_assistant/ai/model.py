import time
from abc import ABC, abstractmethod

from google import genai
from loguru import logger

from product_assistant.core.config import settings

_OVERLOAD_MESSAGE = "LLM модель перегружена. Повторите запрос позже."
_RETRIES = 3
_RETRY_DELAY = 5


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
        for attempt in range(1, _RETRIES + 1):
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
                is_overload = "503" in str(exc) or "UNAVAILABLE" in str(exc)
                if is_overload and attempt < _RETRIES:
                    logger.warning(
                        "Gemini перегружена, попытка {}/{}, повтор через {} сек. Ошибка: {}",
                        attempt, _RETRIES, _RETRY_DELAY, exc,
                    )
                    time.sleep(_RETRY_DELAY)
                    continue

                if is_overload:
                    logger.error("Gemini недоступна после {} попыток", _RETRIES)
                    return _OVERLOAD_MESSAGE

                raise RuntimeError(f"Ошибка Gemini API: {exc}") from exc

        return _OVERLOAD_MESSAGE
