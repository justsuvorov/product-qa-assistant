import asyncio
import os
import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from sqlalchemy.orm import Session

from product_assistant.core.config import settings
from product_assistant.core.database import get_db_connection
from product_assistant.models.schema import DBObject

bot = Bot(token=settings.telegram_bot_token.get_secret_value())
dp = Dispatcher()

FASTAPI_URL = os.getenv("FASTAPI_URL", "http://api:80/api/update")


_BTN_CLEAR = "🗑 Очистить контекст"


def _main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=_BTN_CLEAR)]],
        resize_keyboard=True,
    )


@dp.message(CommandStart())
async def handle_start(message: Message):
    await message.answer(
        "Привет! Я помогу ответить на вопросы по страховым продуктам ВСК.\n\n"
        "Задайте вопрос — например:\n"
        "• Что покрывает КАСКО Классика?\n"
        "• Входит ли эвакуация в КАСКО?\n"
        "• Какие документы нужны для ОСАГО?",
        reply_markup=_main_keyboard(),
    )


@dp.message(F.text == _BTN_CLEAR)
async def handle_clear_context(message: Message):
    db_session = get_db_connection()
    db = DBObject(connection=db_session)
    try:
        db.clear_user_context(message.from_user.id)
    finally:
        db_session.close()
    await message.answer("✅ Контекст диалога очищен. Можете задавать новый вопрос.")


@dp.message(F.text)
async def handle_text(message: Message):
    status_msg = await message.answer("⏳ Запрос получен, ищу информацию...")

    db_session: Session = get_db_connection()
    db = DBObject(connection=db_session)

    status_deleted = False
    try:
        question = db.save_question(
            question_text=message.text,
            user_id=message.from_user.id if message.from_user else None,
        )

        async with httpx.AsyncClient(timeout=120.0) as client:
            payload = {
                "message_id": question.id,
                "user_id": question.user_id,
            }
            response = await client.post(FASTAPI_URL, json=payload)

        await status_msg.delete()
        status_deleted = True

        if response.status_code == 200:
            result = response.json()
            if result.get("context_cleared"):
                await message.answer("🔄 Вопрос про новый продукт. Контекст очищен.")
            answer = result.get("payload", {}).get("text", "Ответ не получен")
            await message.answer(f"✅ {answer}", parse_mode="MarkdownV2", reply_markup=_main_keyboard())
        else:
            await message.answer(
                f"❌ Ошибка сервера ({response.status_code}): {response.text[:500]}",
                reply_markup=_main_keyboard(),
            )

    except Exception as exc:
        if not status_deleted:
            await status_msg.delete()
        await message.answer(f"💥 Произошла ошибка: {exc}", reply_markup=_main_keyboard())
    finally:
        db_session.close()


async def main():
    print("Бот запущен и готов к работе...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
