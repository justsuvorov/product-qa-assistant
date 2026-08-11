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
        self._prompt_engine_common = PromptEngine(role=settings.ai_role_common, template=settings.ai_prompt_template)
        self._mapper = product_mapper or ProductMapper()
        self._list_request_role = settings.ai_list_request_role

    def query(self) -> tuple[str, str | None, int | None, bool]:
        """
        Возвращает (primary_prompt, fallback_prompt, product_id, context_cleared).
        - primary_prompt: промпт для первой попытки (с конкретным продуктом или сразу 'Общий')
        - fallback_prompt: промпт с категорией 'Общий' (если первая попытка вернет NOT_ENOUGH_INFO)
        """
        question_record = self._db.get_question(self._request.message_id)
        logger.info("Вопрос получен: \"{}\"", question_record.question_text[:120])

        is_list_request = _is_product_list_request(question_record.question_text)
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
        def _get_general_info() -> str:
            general_records = [
                p for p in all_products
                if getattr(p, 'category', None) == "Общее" or p.name == "Общее"
            ]
            if general_records:
                content = "\n\n---\n\n".join(p.content for p in general_records if p.content)
                return f"Общие правила и условия страхования:\n\n{content}"
            return "Общая информация о правилах страхования отсутствует в базе."

        # Обработка запроса на СПИСОК продуктов
        if is_list_request:
            logger.info("Запрос на список продуктов — обрабатываем через LLM")
            unique_names = set(p.name for p in all_products if p.name and p.name != "Общий")
            product_list = "\n".join(f"• {name}" for name in unique_names)
            product_info = f"Доступные страховые продукты:\n\n{product_list}"

            list_engine = PromptEngine(role=self._list_request_role, template=self._prompt_engine._template)
            primary_prompt = list_engine.build(question=cleaned, product_info=product_info)
            return primary_prompt, None, None, False

        # ПОИСК конкретного продукта (исключая категорию "Общий")
        specific_products = [
            p for p in all_products
            if getattr(p, 'category', None) != "Общее" and p.name != "Общее"
        ]
        products_matched = _find_best_product(cleaned, specific_products)

        # Если по тексту не нашли — проверяем контекст диалога
        if not products_matched and context:
            last_product = self._db.get_last_product_for_user(self._request.user_id)
            if last_product and last_product.name != "Общее":
                products_matched = [p for p in all_products if p.name == last_product.name]

        # Смена продукта пользователем
        if products_matched and self._request.user_id is not None:
            first_matched = products_matched[0]
            context_product = self._db.get_last_product_for_user(self._request.user_id)
            if context_product is not None and context_product.id != first_matched.id:
                logger.info("Смена продукта: \"{}\" → \"{}\"", context_product.name, first_matched.name)
                self._db.clear_user_context(self._request.user_id)
                context = []
                context_cleared = True

        # СБОРКА ПРОМПТОВ
        if products_matched:
            first_matched = products_matched[0]
            product_id = first_matched.id
            logger.info("Выбран конкретный продукт: \"{}\" (id={})", first_matched.name, product_id)

            # 1. Первичный product_info (только найденный продукт)
            product_content = "\n\n---\n\n".join(p.content for p in products_matched if p.content)
            primary_info = f"Продукт: {first_matched.name}\n\n{product_content}"
            primary_prompt = self._prompt_engine.build(question=cleaned, product_info=primary_info, context=context)

            # 2. Резервный fallback_prompt (готовим с категорией "Общее")
            general_info = _get_general_info()
            fallback_prompt = self._prompt_engine_common.build(question=cleaned, product_info=general_info, context=context)

        else:
            # Конкретный продукт не найден — сразу используем категорию "Общее"
            logger.info("Конкретный продукт не найден — используем базу 'Общее'")
            general_info = _get_general_info()
            primary_prompt = self._prompt_engine_common.build(question=cleaned, product_info=general_info, context=context)
            fallback_prompt = None

        return primary_prompt, fallback_prompt, product_id, context_cleared


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