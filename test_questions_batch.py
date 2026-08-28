"""
Скрипт для батч-тестирования API /api/update.

Перед прогоном вопросов скрипт сам инициализирует БД (создаёт таблицы) и
запускает парсинг источника продуктов согласно текущему .env (SCRAPER_TYPE,
PRODUCTS_WEBSITE_URL / LOCAL_FILES_DIR, PRODUCT_PATHS и т.д.) — той же логикой,
что использует main.py при старте сервиса. Так тест не зависит от того, был ли
уже поднят и наполнен API.

Затем для каждого вопроса:
  1. Создаёт запись UserQuestion в БД напрямую (эмулируя сохранение вопроса ботом).
  2. Отправляет POST /api/update на работающий сервис.
  3. Замеряет время ответа, читает текст ответа и выбранный продукт (из БД).
Результат сохраняется в md-отчёт.

Использование:
    python test_questions_batch.py
    python test_questions_batch.py --base-url http://localhost:8000 --questions test_questions.json
    python test_questions_batch.py --same-session   # вопросы одной сессии (накапливается контекст)
    python test_questions_batch.py --no-scrape       # не парсить заново, использовать то, что уже в БД
"""

import argparse
import json
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import httpx
from loguru import logger

from product_assistant.core.config import settings
from product_assistant.core.database import get_db_connection, init_db
from product_assistant.models.schema import DBObject, UserQuestion
from main import _run_scraping

logger.remove()
logger.add(sys.stderr, level="INFO")

DEFAULT_USER_ID = 999000001


def load_questions(path: str) -> list[str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["questions"]


def save_question(db: DBObject, question_text: str, user_id: int, session_id: str) -> int:
    question = UserQuestion(
        user_id=user_id,
        session_id=session_id,
        question_text=question_text,
        cleaned_text=question_text,
    )
    db.connection.add(question)
    db.connection.commit()
    db.connection.refresh(question)
    return question.id


def call_update(base_url: str, message_id: int, user_id: int, session_id: str, timeout: float) -> tuple[dict | None, float, str | None]:
    """Возвращает (json_ответ, время_сек, текст_ошибки)."""
    payload = {"message_id": message_id, "user_id": user_id, "session_id": session_id}
    start = time.perf_counter()
    try:
        resp = httpx.post(f"{base_url}/api/update", json=payload, timeout=timeout)
        elapsed = time.perf_counter() - start
        if resp.status_code == 200:
            return resp.json(), elapsed, None
        return None, elapsed, f"HTTP {resp.status_code}: {resp.text[:500]}"
    except Exception as exc:
        elapsed = time.perf_counter() - start
        return None, elapsed, f"{type(exc).__name__}: {exc}"


def get_product_name(db: DBObject, message_id: int, products_by_id: dict) -> str:
    row = db.connection.get(UserQuestion, message_id)
    if row is None or row.product_id is None:
        return "—"
    product = products_by_id.get(row.product_id)
    return product.name if product else f"id={row.product_id} (не найден)"


def build_report(results: list[dict]) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(results)
    ok = sum(1 for r in results if r["error"] is None)
    avg_time = sum(r["elapsed"] for r in results) / total if total else 0

    lines = [
        f"# Отчёт по тестированию API — {ts}",
        "",
        f"Всего вопросов: {total} | Успешно: {ok} | Ошибок: {total - ok} | Среднее время: {avg_time:.2f} сек",
        "",
        "## Сводная таблица",
        "",
        "| № | Продукт | Время, сек | Статус |",
        "|---|---------|-----------|--------|",
    ]

    for i, r in enumerate(results, 1):
        status = "OK" if r["error"] is None else "ОШИБКА"
        lines.append(f"| {i} | {r['product']} | {r['elapsed']:.2f} | {status} |")

    lines += ["", "---", "", "## Детали по вопросам", ""]

    for i, r in enumerate(results, 1):
        lines.append(f"### {i}. {r['question']}")
        lines.append("")
        lines.append(f"- **Продукт:** {r['product']}")
        lines.append(f"- **Время:** {r['elapsed']:.2f} сек")
        lines.append(f"- **message_id:** {r['message_id']}")
        lines.append("")
        if r["error"]:
            lines.append(f"**Ошибка:** {r['error']}")
        else:
            lines.append("**Ответ:**")
            lines.append("")
            lines.append(r["answer"])
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Батч-тест API /api/update")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Базовый URL сервиса")
    parser.add_argument("--questions", default="test_questions.json", help="JSON-файл со списком вопросов")
    parser.add_argument("--output", default=None, help="Путь к md-отчёту (по умолчанию — с таймстампом)")
    parser.add_argument("--user-id", type=int, default=DEFAULT_USER_ID, help="user_id для тестовых вопросов")
    parser.add_argument("--same-session", action="store_true",
                         help="Слать все вопросы в рамках одной сессии (накопление контекста диалога)")
    parser.add_argument("--timeout", type=float, default=120.0, help="Таймаут HTTP-запроса, сек")
    parser.add_argument("--no-scrape", action="store_true",
                         help="Не парсить источник продуктов заново, использовать то, что уже в БД")
    args = parser.parse_args()

    questions = load_questions(args.questions)
    logger.info("Загружено вопросов: {}", len(questions))

    logger.info("Инициализация БД (создание таблиц, если их нет)...")
    init_db()

    if args.no_scrape:
        logger.info("--no-scrape: пропускаем парсинг, используем текущее содержимое БД")
    else:
        logger.info("Парсинг источника продуктов согласно .env (SCRAPER_TYPE={})...", settings.scraper_type)
        _run_scraping()

    db_session = get_db_connection()
    db = DBObject(connection=db_session)

    shared_session_id = str(uuid.uuid4())

    try:
        products_by_id = {p.id: p for p in db.get_all_products()}
        logger.info("Продуктов в БД: {}", len(products_by_id))
        if not products_by_id:
            logger.warning("В БД нет ни одного продукта — ответы будут без привязки к продукту")

        results = []
        for i, question in enumerate(questions, 1):
            session_id = shared_session_id if args.same_session else str(uuid.uuid4())

            message_id = save_question(db, question, args.user_id, session_id)
            logger.info("[{}/{}] message_id={} — {}", i, len(questions), message_id, question[:80])

            response, elapsed, error = call_update(
                args.base_url, message_id, args.user_id, session_id, args.timeout
            )

            if error:
                logger.error("  Ошибка: {}", error)
                answer = None
            else:
                answer = response["payload"]["text"]
                logger.info("  Время: {:.2f} сек, длина ответа: {} симв.", elapsed, len(answer))

            product = get_product_name(db, message_id, products_by_id)

            results.append({
                "question": question,
                "message_id": message_id,
                "elapsed": elapsed,
                "answer": answer,
                "error": error,
                "product": product,
            })

        report_md = build_report(results)
        output_path = args.output or f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        Path(output_path).write_text(report_md, encoding="utf-8")
        logger.info("Отчёт сохранён: {}", output_path)

    finally:
        db_session.close()


if __name__ == "__main__":
    main()
