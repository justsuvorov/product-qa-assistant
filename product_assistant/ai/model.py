import re
import time
from abc import ABC, abstractmethod

import httpx
from google import genai
from loguru import logger

from product_assistant.core.config import settings

_OVERLOAD_MESSAGE = "Сервис модели временно недоступен, повторите запрос позже."


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
    Примеры: Qwen, Gemini, OpenAI, YandexGPT.

    Встроенная retry-логика при ошибках сервиса:
    - 503 / UNAVAILABLE / overloaded — 3 попытки с задержкой 5 сек
    - Пустой ответ (ValueError) — 3 попытки с задержкой 1 сек

    Наследник обязан реализовать:
        - _call_api() — один запрос к API без retry
    """

    retries: int = 3
    retry_delay: int = 5
    empty_response_retries: int = 3
    empty_response_delay: int = 3

    @abstractmethod
    def _call_api(self, query: str) -> str:
        """Один вызов API. Должен вернуть текст или выбросить исключение."""

    def response(self, query: str) -> str:
        for attempt in range(1, self.retries + 1):
            try:
                return self._call_api(query)
            except ValueError as exc:
                # Ошибка "не вернул текст" — retry с коротким таймаутом
                if self._is_empty_response(exc) and attempt < self.empty_response_retries:
                    logger.warning(
                        "{} не вернул текст, попытка {}/{}, повтор через {} сек",
                        self.__class__.__name__, attempt, self.empty_response_retries, self.empty_response_delay,
                    )
                    time.sleep(self.empty_response_delay)
                    continue

                if self._is_empty_response(exc):
                    logger.error(
                        "{} не вернул валидный текст после {} попыток",
                        self.__class__.__name__, self.empty_response_retries
                    )
                    return _OVERLOAD_MESSAGE

                # Другие ValueError — сразу ошибка
                raise RuntimeError(f"Ошибка {self.__class__.__name__}: {exc}") from exc

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
        """Проверить что это ошибка перегрузки сервиса."""
        text = str(exc)
        return "503" in text or "UNAVAILABLE" in text or "overloaded" in text.lower()

    @staticmethod
    def _is_empty_response(exc: Exception) -> bool:
        """Проверить что это ошибка пустого ответа."""
        text = str(exc)
        return "не вернул текст" in text.lower() or "no response" in text.lower()


# ==============================================================================
# Реализации
# ==============================================================================
class GeminiModel(ServiceLLMModel):
    """Google Gemini через google-genai SDK."""

    def __init__(self):
        self._client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())
        self._generation_config = genai.types.GenerateContentConfig(
            temperature=settings.ai_temperature,
            top_p=0.95,
            top_k=64,
            max_output_tokens=4096,
        )
        self._model_name = settings.model_name

    def _call_api(self, query: str) -> str:
        result = self._client.models.generate_content(
            model=self._model_name,
            contents=query,
            config=self._generation_config,
        )
        if not result or not result.text:
            raise ValueError("Gemini не вернула текст")
        return result.text.strip()


class QwenModel(ServiceLLMModel):
    """Qwen через OpenAI-совместимый /v1/completions API."""

    def __init__(self):
        self._api_url = settings.qwen_api_url
        self._model_name = settings.qwen_model_name
        self._client = httpx.Client(timeout=120, verify=False)

    def _call_api(self, query: str) -> str:
        resp = self._client.post(
            self._api_url,
            json={
                "model": self._model_name,
                "prompt": query,
                "max_tokens": settings.qwen_max_tokens,
                "enable_thinking": False,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["text"]
        # Qwen3 thinking-модели оборачивают рассуждение в <think>...</think> — убираем
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        if not text:
            raise ValueError("Qwen не вернул текст")
        return text


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
        try:
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
