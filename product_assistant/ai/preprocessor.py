import json
import os
import re
from dataclasses import dataclass
from loguru import logger
from sqlalchemy import update

from product_assistant.ai.promt_builders import PromptEngine
from product_assistant.core.config import settings
from product_assistant.models.schema import DBObject, UserQuestion

# Набор базовых приветствий для фильтрации интентов
GREETINGS_AND_COMMON = {
    "привет", "здравствуйте", "добрый день", "добрый вечер", "доброе утро",
    "приветик", "салют", "hi", "hello", "hey"
}


@dataclass
class ProcessingTask:
    message_id: int
    user_id: int


class ConflictMappingError(Exception):
    """Исключение, выбрасываемое при обнаружении нескольких подходящих продуктов."""

    def __init__(self, products: list):
        self.products = products
        super().__init__(f"Конфликт маппинга: найдено несколько продуктов {products}")


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
        self._aliases = self._load_aliases()

    def _load_aliases(self) -> dict:
        """Считывает словарь синонимов из JSON-файла без изменения кода."""
        path = settings.product_aliases_path
        if not os.path.exists(path):
            logger.warning("Файл маппинга продуктов не найден по пути: {}. Используется пустой маппинг.", path)
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {str(k).lower().strip(): str(v).strip() for k, v in data.items()}
        except Exception as e:
            logger.error("Ошибка при загрузке product_aliases.json: {}", e)
            return {}

    def _normalize_and_map_product(self, cleaned_question: str, all_products) -> object | list | None:
        """
        Ищет совпадения по словарю синонимов/аббревиатур с гибким поиском по базе данных.
        """
        logger.debug("Исходный запрос для маппинга: '{}'", cleaned_question)

        lower_question = cleaned_question.lower()

        # Очистка строки от знаков препинания для проверки на приветствие
        clean_for_check = re.sub(r'[^\w\s]', '', lower_question).strip()
        if clean_for_check in GREETINGS_AND_COMMON:
            logger.info("Запрос распознан как приветствие в маппере. Поиск продуктов пропущен.")
            return None

        found_target_names = set()

        # Helper для очистки названий от кавычек, дефисов и лишних пробелов
        def _simplify_string(s: str) -> str:
            return re.sub(r'[^\w]', '', s.lower())

        # 1. Ищем совпадения по словарю алиасов (product_aliases.json)
        sorted_aliases = sorted(self._aliases.keys(), key=len, reverse=True)
        for alias in sorted_aliases:
            pattern = rf"\b{re.escape(alias)}\b"
            if re.search(pattern, lower_question):
                target_name = self._aliases[alias]
                found_target_names.add(target_name)
                logger.debug("Найден алиас по словарю: '{}' -> '{}'", alias, target_name)

        # 2. Сопоставление с БД по найденным алиасам
        matched_products = []
        if found_target_names:
            for target_name in found_target_names:
                simplified_target = _simplify_string(target_name)

                for product in all_products:
                    simplified_product_name = _simplify_string(product.name)

                    if simplified_target == simplified_product_name:
                        if product not in matched_products:
                            matched_products.append(product)

            if len(matched_products) == 1:
                logger.info("Продукт успешно определен по словарю: {}", matched_products[0].name)
                return matched_products[0]
            elif len(matched_products) > 1:
                logger.warning("Конфликт маппинга по словарю! Найдено несколько продуктов: {}",
                               [p.name for p in matched_products])
                return matched_products

        # 3. Фолбек (Fallback): поиск по пересечению слов
        logger.debug("Синонимы не найдены в БД. Применяю базовый поиск по пересечению слов.")
        question_words = set(re.findall(r'\w+', lower_question))
        best_score = 0
        fallback_products = []

        for product in all_products:
            name_words = set(re.findall(r'\w+', product.name.lower()))
            score = len(name_words & question_words)
            if score > best_score:
                best_score = score
                fallback_products = [product]
            elif score == best_score and score > 0:
                fallback_products.append(product)

        if best_score > 0:
            if len(fallback_products) == 1:
                logger.debug("Продукт найден через базовое пересечение слов: {}", fallback_products[0].name)
                return fallback_products[0]
            else:
                logger.warning("Конфликт базового поиска! Несколько продуктов имеют одинаковый score: {}",
                               [p.name for p in fallback_products])
                return fallback_products

        return None

    def query(self) -> tuple[str, int | None]:
        question_record = self._db.get_question(self._request.message_id)
        cleaned = _clean_text(question_record.question_text)
        context = self._db.get_context(self._request.user_id)

        # Сохраняем очищенный текст в БД
        self._db.connection.execute(
            update(UserQuestion)
            .where(UserQuestion.id == self._request.message_id)
            .values(cleaned_text=cleaned)
        )
        self._db.connection.commit()

        # === ПРОВЕРКА НА ОБЩЕЕ ПРИВЕТСТВИЕ И СВОБОДНЫЙ ДИАЛОГ ===
        clean_for_greeting = re.sub(r'[^\w\s]', '', cleaned.lower()).strip()

        if clean_for_greeting in GREETINGS_AND_COMMON:
            logger.info("Обнаружено общее приветствие '{}'. Переключение в режим свободного диалога.", cleaned)
            product_id = None
            enriched_question = cleaned
            product_info = (
                "[СИСТЕМНОЕ УВЕДОМЛЕНИЕ]: Пользователь просто поздоровался или отправил общую фразу. "
                "Конкретный продукт еще не выбран. Поприветствуй пользователя в ответ от лица умного "
                "страхового ассистента и вежливо уточни, по какому продукту (например, КАСКО или ОСАГО) "
                "ему необходима консультация."
            )
        else:
            # Если это не приветствие, выполняем стандартный поиск продуктов
            products = self._db.get_all_products()
            mapped_result = self._normalize_and_map_product(cleaned, products)

            if isinstance(mapped_result, list):
                raise ConflictMappingError(mapped_result)

            product = mapped_result

            # Подтягиваем прошлый продукт из контекста, только если текущий запрос — не приветствие
            if product is None and context:
                product = self._db.get_last_product_for_user(self._request.user_id)

            if product:
                product_info = f"Продукт: {product.name}\n\n{product.content}"
                product_id = product.id

                # === ДИАГНОСТИЧЕСКИЙ БЛОК ===
                logger.info("=== ПРОВЕРКА СОДЕРЖИМОГО ТЕКСТА ИЗ POSTGRES ===")
                logger.info("ID продукта: {}, Название: {}", product.id, product.name)

                product_content_lower = product.content.lower() if product.content else ""
                has_kkp = "ккп" in product_content_lower
                has_compact_plus = "компакт плюс" in product_content_lower
                has_kkm = "ккм" in product_content_lower

                logger.info("Содержит ли текст аббревиатуру 'ккп': {}", has_kkp)
                logger.info("Содержит ли текст фразу 'компакт плюс': {}", has_compact_plus)
                logger.info("Содержит ли текст аббревиатуру 'ккм': {}", has_kkm)
                logger.info("Длина всего текста продукта: {} символов", len(product_content_lower))
                logger.info("==============================================")

                # --- БЛОК ОБОГАЩЕНИЯ ВОПРОСА С ДИРЕКТИВОЙ ДЛЯ ПОДПРОДУКТОВ ---
                lower_question = cleaned.lower()

                def _simplify_string(s: str) -> str:
                    return re.sub(r'[^\w]', '', s.lower())

                matched_aliases = []
                simplified_product_name = _simplify_string(product.name)

                for alias, target in self._aliases.items():
                    simplified_target = _simplify_string(target)
                    if alias in lower_question and (
                            simplified_target == simplified_product_name or
                            simplified_target in simplified_product_name or
                            simplified_product_name in simplified_target
                    ):
                        matched_aliases.append(alias)

                if matched_aliases and len(cleaned) < 50:
                    logger.debug("Добавляем точечный контекст алиаса для LLM: {}", matched_aliases)

                    if any(x in ["ккп", "каско компакт плюс"] for x in
                           matched_aliases) and simplified_product_name == "каско":
                        enriched_question = (
                            f"{cleaned}\n\n"
                            f"[СИСТЕМНАЯ ДИРЕКТИВА ДЛЯ LLM]: Внимательно изучи предоставленный текст продукта КАСКО. "
                            f"Тебе нужно найти информацию, относящуюся СТРОГО к программе 'Компакт Плюс' (или 'Каско Компакт Плюс'). "
                            f"Игнорируй базовые условия обычного КАСКО и сформируй ответ только на основе правил секции 'Компакт Плюс'."
                        )
                    else:
                        enriched_question = (
                            f"{cleaned} (Внимание: Ищи в предоставленном тексте информацию, относящуюся к: {', '.join(matched_aliases)}."
                        )
                else:
                    enriched_question = cleaned
            else:
                product_info = "Информация о продукте не найдена в базе данных."
                product_id = None
                enriched_question = cleaned

        # Сборка финального промпта
        if context:
            prompt = self._prompt_engine.build(question=enriched_question, product_info=product_info, context=context)
        else:
            prompt = self._prompt_engine.build(question=enriched_question, product_info=product_info)

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