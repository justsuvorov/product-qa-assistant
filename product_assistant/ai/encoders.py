import whisper
import os
import torch
from abc import ABC, abstractmethod


class Encoder(ABC):
    @abstractmethod
    def prepared_data(self, source: str) -> str:
        pass


class TextEncoder(Encoder):
    def __init__(self, ):
        """

        """
        pass

    def prepared_data(self, text: str) -> str:
        """
        Готовит текст из сообщения в тело запроса для LLM
        """
        result = {}
        result['text'] = text

        return result["text"].strip()

