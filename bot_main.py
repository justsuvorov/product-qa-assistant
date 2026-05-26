import asyncio
import os
import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.client.session.aiohttp import AiohttpSession
from sqlalchemy.orm import Session

from product_assistant.core.config import settings
from product_assistant.core.database import get_db_connection
from product_assistant.models.schema import DBObject

_proxy_url = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
_session = AiohttpSession(proxy=_proxy_url) if _proxy_url else None
bot = Bot(token=settings.telegram_bot_token.get_secret_value(), session=_session)
dp = Dispatcher()

FASTAPI_URL = os.getenv("FASTAPI_URL", "http://api:80/api/update")


@dp.message(F.text)
async def handle_text(message: Message):
    status_msg = await message.answer("⏳ Запрос получен, ищу информацию...")

    db_session: Session = get_db_connection()
    db = DBObject(connection=db_session)

    try:
        # Сохраняем вопрос в БД
        question = db.save_question(
            question_text=message.text,
            user_id=message.from_user.id if message.from_user else None,
        )

        # Отправляем в FastAPI для обработки
        async with httpx.AsyncClient(timeout=120.0) as client:
            payload = {"message_id": question.id}
            response = await client.post(FASTAPI_URL, json=payload)

        if response.status_code == 200:
            result = response.json()
            answer = result.get("payload", {}).get("text", "Ответ не получен")
            await status_msg.edit_text(f"✅ {answer}", parse_mode="MarkdownV2")
        else:
            await status_msg.edit_text(
                f"❌ Ошибка сервера ({response.status_code}): {response.text}"
            )

    except Exception as exc:
        await status_msg.edit_text(f"💥 Произошла ошибка: {exc}")
    finally:
        db_session.close()


async def main():
    print("Бот запущен и готов к работе...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
