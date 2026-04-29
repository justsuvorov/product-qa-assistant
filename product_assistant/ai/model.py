import time
from abc import ABC, abstractmethod

from loguru import logger

_OVERLOAD_MESSAGE = "LLM модель перегружена. Повторите запрос позже."


# ==============================================================================
# Базовый интерфейс
# ==============================================================================

class AIModel(ABC):
    """Базовый интерфейс для всех LLM-моделей."""

    @abstractmethod
    def response(self, query: str) -> str:
        """Принимает промпт, возвращает текстовый ответ."""


# ==============================================================================
# Локальные модели (запущены в RAM на том же хосте)
# ==============================================================================

class LocalAIModel(AIModel, ABC):
    """
    Интерфейс для локальных LLM-моделей, работающих в оперативной памяти.
    Примеры: Ollama, llama.cpp, LM Studio, GPT4All.

    Наследник обязан реализовать:
        - load_model() — загрузка весов в RAM
        - response()   — генерация ответа
    """

    def __init__(self, model_name: str, **kwargs):
        self._model_name = model_name
        self._model = None
        self.load_model(**kwargs)

    @abstractmethod
    def load_model(self, **kwargs):
        """Загружает модель в оперативную память."""

    @abstractmethod
    def response(self, query: str) -> str:
        """Генерирует ответ локальной моделью."""

    def is_loaded(self) -> bool:
        return self._model is not None


# ==============================================================================
# Внешние сервисы (API-модели)
# ==============================================================================

class ServiceLLMModel(AIModel, ABC):
    """
    Интерфейс для LLM-моделей, доступных через внешний API.
    Примеры: Gemini, OpenAI, YandexGPT, GigaChat, Claude.

    Встроенная retry-логика при перегрузке сервиса (503 / UNAVAILABLE).
    Наследник обязан реализовать:
        - _call_api() — один запрос к API без retry
    """

    # Переопределяй в наследнике при необходимости
    retries: int = 3
    retry_delay: int = 5

    @abstractmethod
    def _call_api(self, query: str) -> str:
        """Один вызов API. Должен вернуть текст или выбросить исключение."""

    def response(self, query: str) -> str:
        for attempt in range(1, self.retries + 1):
            try:
                return self._call_api(query)
            except Exception as exc:
                if self._is_overload(exc) and attempt < self.retries:
                    logger.warning(
                        "{} перегружен, попытка {}/{}, повтор через {} сек. Ошибка: {}",
                        self.__class__.__name__, attempt, self.retries, self.retry_delay, exc,
                    )
                    time.sleep(self.retry_delay)
                    continue

                if self._is_overload(exc):
                    logger.error("{} недоступен после {} попыток", self.__class__.__name__, self.retries)
                    return _OVERLOAD_MESSAGE

                raise RuntimeError(f"Ошибка {self.__class__.__name__}: {exc}") from exc

        return _OVERLOAD_MESSAGE

    @staticmethod
    def _is_overload(exc: Exception) -> bool:
        text = str(exc)
        return "503" in text or "UNAVAILABLE" in text or "overloaded" in text.lower()


# ==============================================================================
# Реализации
# ==============================================================================

class GeminiModel(ServiceLLMModel):
    """Google Gemini через google-genai SDK."""

    def __init__(self):
        from google import genai
        from product_assistant.core.config import settings

        self._client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())
        self._generation_config = genai.types.GenerateContentConfig(
            temperature=settings.ai_temperature,
            top_p=0.95,
            top_k=64,
            max_output_tokens=4096,
        )
        self._model_name = settings.model_name

    def _call_api(self, query: str) -> str:
        from product_assistant.core.config import settings

        result = self._client.models.generate_content(
            model=self._model_name,
            contents=query,
            config=self._generation_config,
        )
        if not result or not result.text:
            raise ValueError("Gemini не вернула текст")
        return result.text.strip()


class OllamaModel(LocalAIModel):
    """
    Локальная модель через Ollama (https://ollama.com).
    Ollama должен быть запущен отдельно: `ollama serve`.

    Пример:
        model = OllamaModel(model_name="llama3", base_url="http://localhost:11434")
    """

    def __init__(self, model_name: str, base_url: str = "http://localhost:11434"):
        self._base_url = base_url
        super().__init__(model_name=model_name)

    def load_model(self, **kwargs):
        # Ollama управляет моделью сам — проверяем только доступность сервера
        try:
            import httpx
            resp = httpx.get(f"{self._base_url}/api/tags", timeout=5)
            resp.raise_for_status()
            available = [m["name"] for m in resp.json().get("models", [])]
            if self._model_name not in available:
                logger.warning(
                    "Ollama: модель '{}' не найдена. Доступные: {}",
                    self._model_name, available,
                )
            else:
                logger.info("Ollama: модель '{}' готова", self._model_name)
            self._model = True
        except Exception as exc:
            logger.error("Ollama недоступен ({}): {}", self._base_url, exc)
            self._model = None

    def response(self, query: str) -> str:
        import httpx

        if not self.is_loaded():
            raise RuntimeError("Ollama сервер недоступен")

        try:
            resp = httpx.post(
                f"{self._base_url}/api/generate",
                json={"model": self._model_name, "prompt": query, "stream": False},
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json()["response"].strip()
        except Exception as exc:
            raise RuntimeError(f"Ошибка Ollama: {exc}") from exc
