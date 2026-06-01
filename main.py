import asyncio
import traceback
from contextlib import asynccontextmanager

from loguru import logger
from pydantic import BaseModel

from fastapi import FastAPI, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from product_assistant.ai.model import GeminiModel, OllamaModel
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
    init_db()
    logger.info("Запуск парсинга сайта продуктов...")
    # Playwright Sync API нельзя вызывать из asyncio event loop напрямую.
    # asyncio.to_thread запускает _run_scraping в отдельном потоке без event loop.
    await asyncio.to_thread(_run_scraping)
    yield


app = FastAPI(lifespan=lifespan)

class ClearContextRequest(BaseModel):
    user_id: int


@app.post("/api/update")
def process_question(request: APIRequest):
    task = ProcessingTask(message_id=request.message_id, user_id=request.user_id)
    logger.info("Запрос получен: message_id={}", request.message_id)

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
        ai_model=OllamaModel(model_name='gemma4:31b-cloud', base_url="http://localhost:11434"),
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


@app.post("/api/clear-context")
def clear_user_context_endpoint(request: ClearContextRequest):
    logger.info("Получен запрос на очистку контекста для user_id={}", request.user_id)

    db_session = get_db_connection()
    db = DBObject(connection=db_session)

    try:
        # Вызываем метод очистки из schema.py
        success = db.clear_user_context(request.user_id)

        if success:
            return JSONResponse(
                content={"status": "success", "message": "Контекст успешно очищен. Начат новый диалог!"},
                status_code=status.HTTP_200_OK
            )
        else:
            return JSONResponse(
                content={"error": "Не удалось сбросить контекст для данного пользователя."},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    except Exception:
        error_trace = traceback.format_exc()
        logger.error("Критическая ошибка при очистке контекста:\n{}", error_trace)
        error = {"error": error_trace}
        return JSONResponse(content=jsonable_encoder(error), status_code=status.HTTP_400_BAD_REQUEST)
    finally:
        db_session.close()