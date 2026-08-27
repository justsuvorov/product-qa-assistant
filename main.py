import asyncio
import traceback
from contextlib import asynccontextmanager

from loguru import logger

from fastapi import FastAPI, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, PlainTextResponse

from product_assistant.ai.model import QwenModel, GeminiModel
from product_assistant.ai.postprocessor import PostProcessor
from product_assistant.ai.preprocessor import TextPreprocessor, ProcessingTask, _clean_text, _find_best_product
from product_assistant.ai.product_mapper import ProductMapper
from product_assistant.ai.promt_builders import PromptEngine
from product_assistant.core.config import settings
from product_assistant.core.database import get_db_connection, init_db
from product_assistant.models.request import APIRequest
from product_assistant.models.schema import DBObject
from product_assistant.reports.report_export import ReportExport
from product_assistant.scraper import create_scraper
from product_assistant.services.assistant import AIAssistantService


def _run_scraping():
    """Парсит сайт и сохраняет продукты в БД."""
    paths = [p.strip() for p in settings.product_paths.split(",") if p.strip()] or None

    logger.info("Инициализация скрэйпера: type={}, url={}, auth={}",
                settings.scraper_type,
                settings.products_website_url,
                "enabled" if settings.scraper_username else "disabled")

    scraper = create_scraper(
        scraper_type=settings.scraper_type,
        base_url=settings.products_website_url,
        product_paths=paths,
        selenium_url=settings.selenium_url,
        username=settings.scraper_username,
        password=settings.scraper_password,
        local_files_dir=settings.local_files_dir,
    )
    products = scraper.scrape_all()

    if not products:
        logger.warning("Парсинг не вернул ни одного продукта")
        return

    db_session = get_db_connection()
    db = DBObject(connection=db_session)
    try:
        for item in products:
            db.upsert_product(name=item["name"], url=item["url"], content=item["content"])
        logger.info("Продукты успешно сохранены в БД: %d шт.", len(products))
    finally:
        db_session.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Запуск парсинга сайта продуктов...")
    # Playwright Sync API нельзя вызывать из asyncio event loop напрямую.
    # asyncio.to_thread запускает _run_scraping в отдельном потоке без event loop.
    await asyncio.to_thread(_run_scraping)
    yield


app = FastAPI(lifespan=lifespan)
product_mapper = ProductMapper(aliases_path=settings.product_aliases_path)

@app.post("/api/update")
def process_question(request: APIRequest):
    task = ProcessingTask(message_id=request.message_id, user_id=request.user_id)
    logger.info("━━━ Новый запрос: message_id={}, user_id={} ━━━", request.message_id, request.user_id)

    db_session = get_db_connection()
    db = DBObject(connection=db_session)

    ai = AIAssistantService(
        preprocessor=TextPreprocessor(
            db_object=db,
            request=task,
            prompt_engine=PromptEngine(
                role=settings.ai_role,
                template=settings.ai_prompt_template,
            ),
            product_mapper=product_mapper,
        ),
        postprocessor=PostProcessor(),
        ai_model=QwenModel(),
        report_export=ReportExport(db_object=db, processing_task=task),
    )

    try:
        response = ai.result()
        logger.info("━━━ Запрос message_id={} завершён успешно ━━━", request.message_id)
        return JSONResponse(content=jsonable_encoder(response), status_code=status.HTTP_200_OK)
    except Exception:
        logger.error("━━━ Запрос message_id={} завершён с ошибкой:\n{} ━━━", request.message_id, traceback.format_exc())
        error = {"error": traceback.format_exc()}
        return JSONResponse(content=jsonable_encoder(error), status_code=status.HTTP_400_BAD_REQUEST)
    finally:
        db_session.close()


@app.get("/api/debug/prompt")
def debug_prompt(q: str = Query(..., description="Вопрос для отладки")):
    """Строит промпт для LLM по вопросу и возвращает markdown."""
    from datetime import datetime

    db_session = get_db_connection()
    db = DBObject(connection=db_session)

    try:
        cleaned = _clean_text(q)
        normalized = product_mapper.normalize(cleaned)
        all_products = db.get_all_products()

        products = _find_best_product(normalized, all_products)

        if products:
            product_name = products[0].name
            product_id = getattr(products[0], 'id', None)

            combined_content = "\n\n---\n\n".join(
                p.content for p in products if p.content
            )

            product_info = f"Продукт: {product_name}\n\n{combined_content}"
        else:
            product_info = "Информация о продукте не найдена в базе данных."
            product_id = None
            product_name = None

        engine = PromptEngine(role=settings.ai_role, template=settings.ai_prompt_template)
        prompt = engine.build(question=normalized, product_info=product_info)

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        md = f"""# Debug Prompt — {ts}
...

## Вопрос
```
{q}
```

## После нормализации
```
{normalized}
```

## Метаданные
| Поле | Значение |
|------|---------|
| product_id | {product_id} |
| product_name | {product_name} |
| Продуктов в БД | {len(products)} |
| Длина промпта | {len(prompt)} символов |

## Полный промпт для LLM

```
{prompt}
```
"""
        return PlainTextResponse(content=md, media_type="text/markdown; charset=utf-8")

    finally:
        db_session.close()
