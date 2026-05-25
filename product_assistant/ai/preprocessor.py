import re
from dataclasses import dataclass

from sqlalchemy import update

from product_assistant.ai.promt_builders import PromptEngine
from product_assistant.models.schema import DBObject, UserQuestion


@dataclass
class ProcessingTask:
    message_id: int
    user_id: int = None


class Preprocessor:
    def query(self):
        raise NotImplementedError


class TextPreprocessor(Preprocessor):
    """
    Очищает текст вопроса, ищет подходящий продукт, строит промпт для LLM.
    Возвращает (prompt_str, product_id | None).
    """

    def __init__(self, db_object: DBObject, request: ProcessingTask, prompt_engine: PromptEngine):
        self._db = db_object
        self._request = request
        self._prompt_engine = prompt_engine

    def query(self) -> tuple[str, int | None]:
        question_record = self._db.get_question(self._request.message_id)
        cleaned = _clean_text(question_record.question_text)

        # Сохраняем очищенный текст
        self._db.connection.execute(
            update(UserQuestion)
            .where(UserQuestion.id == self._request.message_id)
            .values(cleaned_text=cleaned)
        )
        self._db.connection.commit()

        products = self._db.get_all_products()
        product = _find_best_product(cleaned, products)

        if product:
            product_info = f"Продукт: {product.name}\n\n{product.content}"
            product_id = product.id
        else:
            product_info = "Информация о продукте не найдена в базе данных."
            product_id = None

        prompt = self._prompt_engine.build(question=cleaned, product_info=product_info)
        return prompt, product_id


def _clean_text(text: str) -> str:
    """Базовая очистка: лишние пробелы, спецсимволы."""
    text = text.strip()
    text = re.sub(r'\s+', ' ', text)
    return text


def _find_best_product(question: str, products) -> object | None:
    """
    Поиск продукта по пересечению слов из вопроса и имени продукта.
    Возвращает лучший результат или None, если совпадений нет.
    """
    if not products:
        return None

    question_words = set(re.findall(r'\w+', question.lower()))
    best_score = 0
    best_product = None

    for product in products:
        name_words = set(re.findall(r'\w+', product.name.lower()))
        score = len(name_words & question_words)
        if score > best_score:
            best_score = score
            best_product = product

    return best_product if best_score > 0 else None
