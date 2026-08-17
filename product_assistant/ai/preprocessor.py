import re
from dataclasses import dataclass
from typing import Union, List

import numpy as np
from loguru import logger
from sqlalchemy import update
from rapidfuzz import process, fuzz
from sentence_transformers import CrossEncoder

from product_assistant.ai.product_mapper import BaseProductMapper, ProductMapper
from product_assistant.ai.promt_builders import PromptEngine
from product_assistant.models.schema import DBObject, UserQuestion

reranker = CrossEncoder('./models/bge-reranker-v2-m3')

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

    def __init__(
        self,
        db_object: DBObject,
        request: ProcessingTask,
        prompt_engine: PromptEngine,
        product_mapper: BaseProductMapper | None = None,
    ):
        from product_assistant.core.config import settings

        self._db = db_object
        self._request = request
        self._prompt_engine = prompt_engine
        self._prompt_engine_common = PromptEngine(role=settings.ai_role_common, template=settings.ai_prompt_template)
        self._mapper = product_mapper or ProductMapper()
        self._list_request_role = settings.ai_list_request_role

    def query(self) -> tuple[str, tuple[str, int | None] | None, int | None, bool]:
        """
        Возвращает (primary_prompt, fallback_prompt, product_id, context_cleared).
        - primary_prompt: промпт для первой попытки (с конкретным продуктом или сразу 'Общий')
        - fallback_prompt: промпт с категорией 'Общий' (если первая попытка вернет NOT_ENOUGH_INFO)
        """
        question_record = self._db.get_question(self._request.message_id)
        logger.info("Вопрос получен: \"{}\"", question_record.question_text[:120])

        cleaned = _clean_text(question_record.question_text)
        cleaned = self._mapper.normalize(cleaned)

        context = self._db.get_context(self._request.user_id)

        # Сохраняем очищенный текст
        self._db.connection.execute(
            update(UserQuestion)
            .where(UserQuestion.id == self._request.message_id)
            .values(cleaned_text=cleaned)
        )
        self._db.connection.commit()

        all_products = self._db.get_all_products()
        context_cleared = False
        product_id = None
        fallback_prompt = None

        # Вспомогательная функция для получения текста категории "Общий"
        def _get_general_info() -> tuple[str, int | None]:
            general_records = [
                p for p in all_products
                if getattr(p, 'category', None) == "Общее" or p.name == "Общее"
            ]
            gen_id = general_records[0].id if general_records else None
            if general_records:
                content = "\n\n---\n\n".join(p.content for p in general_records if p.content)
                return f"Общие правила и условия страхования:\n\n{content}", gen_id
            return "Общая информация о правилах страхования отсутствует в базе.", None

        # ПОИСК конкретного продукта (исключая категорию "Общий")
        specific_products = [
            p for p in all_products
            if getattr(p, 'category', None) != "Общее" and p.name != "Общее"
        ]
        products_matched = _find_best_product(cleaned, specific_products)

        # СБОРКА ПРОМПТОВ
        if products_matched:
            first_matched = products_matched[0]
            product_id = first_matched.id
            logger.info("Выбран конкретный продукт: \"{}\" (id={})", first_matched.name, product_id)

            product_content = "\n\n---\n\n".join(p.content for p in products_matched if p.content)
            primary_info = f"Продукт: {first_matched.name}\n\n{product_content}"
            primary_prompt = self._prompt_engine.build(question=cleaned, product_info=primary_info, context=context)

            # Готовим fallback как пара: (промпт, id_продукта_общее)
            general_info, general_product_id = _get_general_info()
            fallback_prompt = self._prompt_engine_common.build(question=cleaned, product_info=general_info,
                                                               context=context)
            fallback = (fallback_prompt, general_product_id)

        else:
            # Конкретный продукт не найден — сразу подставляем 'Общее' и его product_id
            logger.info("Конкретный продукт не найден — используем базу 'Общее'")
            general_info, product_id = _get_general_info()
            primary_prompt = self._prompt_engine_common.build(question=cleaned, product_info=general_info,
                                                              context=context)
            fallback = None

        return primary_prompt, fallback, product_id, context_cleared


_DIRECT_ANSWER_PREFIX = "\x00DIRECT\x00"


def _clean_text(text: str) -> str:
    """Базовая очистка: лишние пробелы, спецсимволы."""
    text = text.strip()
    text = re.sub(r'\s+', ' ', text)
    return text

def _find_best_product(question: str, products: list) -> list:
  """Использует RapidFuzz для отбора кандидатов и Cross-Encoder для точного ранжирования."""
  if not question or not products:
    return []

  # Быстрый нечеткий поиск кандидатов
  fuzzy_candidates = process.extract(
      question,
      list(dict.fromkeys([p.name for p in products])),
      scorer=fuzz.token_set_ratio,
      limit=10,
  )
  if not fuzzy_candidates or fuzzy_candidates[0][1] < 30:
    logger.warning("Не найдены продукты, совпадающие с текстом вопроса")
    return []

  candidate_names = [item[0] for item in fuzzy_candidates]
  logger.info(f"Совпадения продуктов по тексту вопроса: {candidate_names}")

  # Оценка через Cross-Encoder
  pairs = [[question, name] for name in candidate_names]
  raw_scores = reranker.predict(pairs)

  # Ранжирование по убыванию скора
  ranked_results = sorted(
      zip(candidate_names, raw_scores), key=lambda x: x[1], reverse=True
  )

  logger.info(f"Ранжированные продукты: {ranked_results}")

  best_product, best_score = ranked_results[0]

  # Проверка правила отсечения, если кандидатов больше 1
  if len(ranked_results) > 1:
    second_product, second_score = ranked_results[1]

    # Определяем разницу между первым и вторым местом
    # 1e-9 чтобы не делить на 0
    score_ratio = (best_score + 1e-9) / (second_score + 1e-9)
    abs_margin = best_score - second_score

    logger.info(
        f"Top-1: '{best_product}' ({best_score:.6f}) | "
        f"Top-2: '{second_product}' ({second_score:.6f}) | "
        f"Ratio: {score_ratio:.2f}x | Margin: {abs_margin:.6f}"
    )

    # Условия отсечения:
    MIN_RATIO = 1.5  # Top-1 должен превышать Top-2 хотя бы в 1.5 раза
    MIN_ABS_MARGIN = 0.005  # Либо разница между ними от 0.005
    MIN_ABSOLUTE_SCORE = 0.0005  # Защита от случая, когда все скоры порядка ~0.000001

    is_clear_winner = (
        score_ratio >= MIN_RATIO or abs_margin >= MIN_ABS_MARGIN
    ) and (best_score >= MIN_ABSOLUTE_SCORE)

    if not is_clear_winner:
      logger.warning(
        "Явный лидер не выявлен: недостаточное превосходство Top-1 над Top-2"
        f" (Ratio: {score_ratio:.2f} < {MIN_RATIO}, Margin: {abs_margin:.6f} <"
        f" {MIN_ABS_MARGIN})"
      )
      return []

  # Если кандидат всего один, проверяем только базовый минимальный уровень
  else:
    if best_score < 0.0005:
      logger.warning(
          f"Единственный кандидат '{best_product}' имеет слишком низкий скор"
          f" ({best_score})"
      )
      return []

  return [p for p in products if p.name == best_product]