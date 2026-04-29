import traceback
from contextlib import asynccontextmanager

from loguru import logger

from fastapi import FastAPI, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from product_assistant.ai.model import GeminiModel
from product_assistant.ai.postprocessor import PostProcessor
from product_assistant.ai.preprocessor import TextPreprocessor, ProcessingTask
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
    scraper = create_scraper(
        scraper_type=settings.scraper_type,
        base_url=settings.products_website_url,
        product_paths=paths,
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
    # Создаём таблицы и парсим сайт при старте
    init_db()
    logger.info("Запуск парсинга сайта продуктов...")
    _run_scraping()
    yield


app = FastAPI(lifespan=lifespan)


@app.post("/api/update")
def process_question(request: APIRequest):
    task = ProcessingTask(message_id=request.message_id, user_id=request.user_id)
    logger.info("Запрос получен: message_id=%d", request.message_id)

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
        ),
        postprocessor=PostProcessor(),
        ai_model=GeminiModel(),
        report_export=ReportExport(db_object=db, processing_task=task),
    )

    try:
        response = ai.result()
        return JSONResponse(content=jsonable_encoder(response), status_code=status.HTTP_200_OK)
    except Exception:
        error = {"error": traceback.format_exc()}
        return JSONResponse(content=jsonable_encoder(error), status_code=status.HTTP_400_BAD_REQUEST)
    finally:
        db_session.close()
