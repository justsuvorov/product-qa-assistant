import re
from dataclasses import dataclass

from loguru import logger
from sqlalchemy import update

from product_assistant.ai.product_mapper import BaseProductMapper, ProductMapper
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
        self._mapper = product_mapper or ProductMapper()
        self._list_request_role = settings.ai_list_request_role

    def query(self) -> tuple[str, int | None, bool]:
        """Возвращает (prompt_or_direct_answer, product_id, context_cleared)."""
        question_record = self._db.get_question(self._request.message_id)
        logger.info("Вопрос получен: \"{}\"", question_record.question_text[:120])

        # Проверяем если это запрос на список продуктов
        is_list_request = _is_product_list_request(question_record.question_text)
        if is_list_request:
            logger.info("Запрос на список продуктов/возможностей — обрабатываем через LLM")
            all_products = self._db.get_all_products()
            if all_products:
                unique_names = set(p.name for p in all_products if p.name)
                product_list = "\n".join(f"• {name}" for name in unique_names)
                product_info = f"Доступные страховые продукты:\n\n{product_list}"
            else:
                product_info = "Информация о продуктах ещё не загружена."
        else:
            product_info = None

        cleaned = _clean_text(question_record.question_text)
        cleaned = self._mapper.normalize(cleaned)
        if cleaned != question_record.question_text:
            logger.info("После нормализации: \"{}\"", cleaned[:120])

        context = self._db.get_context(self._request.user_id)
        logger.info("Контекст диалога: {} сообщений (user_id={})", len(context), self._request.user_id)

        self._db.connection.execute(
            update(UserQuestion)
            .where(UserQuestion.id == self._request.message_id)
            .values(cleaned_text=cleaned)
        )
        self._db.connection.commit()

        all_products = self._db.get_all_products()
        logger.info("Продуктов в БД: {}", len(all_products))

        context_cleared = False
        product_id = None

        # Если это запрос на список продуктов — используем специальный product_info
        if is_list_request:
            logger.info("Используем список продуктов как контекст для LLM")
            products_matched = []
        else:
            # _find_best_product теперь возвращает список совпавших строк [Product, Product, ...]
            products_matched = _find_best_product(cleaned, all_products)

            # Берем ID и Name из первого продукта в списке (если нашли)
            first_matched = products_matched[0] if products_matched else None

            # Проверяем смену продукта: если в вопросе явно найден другой продукт чем в контексте
            if first_matched is not None and self._request.user_id is not None:
                context_product = self._db.get_last_product_for_user(self._request.user_id)
                if context_product is not None and context_product.id != first_matched.id:
                    logger.info(
                        "Смена продукта: \"{}\" → \"{}\", контекст очищен",
                        context_product.name, first_matched.name,
                    )
                    self._db.clear_user_context(self._request.user_id)
                    context = []
                    context_cleared = True

            # Если по тексту ничего не нашли — пробуем достать из контекста пользователя
            if not products_matched and context:
                logger.info("Продукт по тексту не найден — берём из контекста пользователя")
                last_product = self._db.get_last_product_for_user(self._request.user_id)
                if last_product:
                    # Если в контексте лежал продукт, ищем все строки для него
                    products_matched = [p for p in all_products if p.name == last_product.name]

            if products_matched:
                first_matched = products_matched[0]
                logger.info("Выбран продукт: \"{}\" (id={})", first_matched.name, first_matched.id)

                # Склеиваем контент со всех строк продукта через разделитель
                combined_content = "\n\n---\n\n".join(
                    p.content for p in products_matched if getattr(p, 'content', None)
                )

                product_info = f"Продукт: {first_matched.name}\n\n{combined_content}"
                product_id = first_matched.id
            else:
                logger.warning("Продукт не найден — ответ без контекста продукта")
                product_info = "Информация о продукте не найдена в базе данных."

        # Для запроса на список продуктов используем специальную роль
        if is_list_request:
            list_engine = PromptEngine(role=self._list_request_role, template=self._prompt_engine._template)
            prompt = list_engine.build(question=cleaned, product_info=product_info)
        else:
            if context:
                prompt = self._prompt_engine.build(question=cleaned, product_info=product_info, context=context)
            else:
                prompt = self._prompt_engine.build(question=cleaned, product_info=product_info)

        return prompt, product_id, context_cleared


_DIRECT_ANSWER_PREFIX = "\x00DIRECT\x00"

_LIST_REQUEST_PATTERN = re.compile(
    r"(что|чем)\s+(ты\s+)?(умеешь|можешь|знаешь)"
    r"|какие\s+(есть\s+)?(продукт|программ|страховк|полис)"
    r"|(список|перечень)\s+(продукт|программ|страховк|страховок|полис)"
    r"|доступные\s+(продукт|программ|страховк)"
    r"|(помощь|помоги|помогите|справка)",
    re.IGNORECASE,
)


def _is_product_list_request(text: str) -> bool:
    return bool(_LIST_REQUEST_PATTERN.search(text))


def _clean_text(text: str) -> str:
    """Базовая очистка: лишние пробелы, спецсимволы."""
    text = text.strip()
    text = re.sub(r'\s+', ' ', text)
    return text


def _find_best_product(question: str, products: list) -> list:
    """
    Ищет наилучший продукт по названию и возвращает ВСЕ строки/записи,
    связанные с этим продуктом.
    """
    if not products:
        return []

    question_words = set(re.findall(r'\w+', question.lower()))
    best_score = 0
    best_product_name = None

    for product in products:
        name_words = set(re.findall(r'\w+', product.name.lower()))
        score = len(name_words & question_words)
        if score > best_score:
            best_score = score
            best_product_name = product.name

    if best_score == 0 or not best_product_name:
        return []

    return [p for p in products if p.name == best_product_name]