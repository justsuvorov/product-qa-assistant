import asyncio
import os
import httpx
from loguru import logger
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.client.session.aiohttp import AiohttpSession
from sqlalchemy.orm import Session

from product_assistant.core.config import settings
from product_assistant.core.database import get_db_connection
from product_assistant.models.schema import DBObject

# Настройка прокси
_proxy_url = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
_session = AiohttpSession(proxy=_proxy_url) if _proxy_url else None
bot = Bot(token=settings.telegram_bot_token.get_secret_value(), session=_session)
dp = Dispatcher()

# Настройка URL бэкенда FastAPI
FASTAPI_BASE_URL = os.getenv("FASTAPI_BASE_URL", "http://127.0.0.1:8000")
FASTAPI_UPDATE_URL = f"{FASTAPI_BASE_URL}/api/update"
FASTAPI_CLEAR_URL = f"{FASTAPI_BASE_URL}/api/clear-context"


def get_main_keyboard():
    """Создает нижнее меню с кнопкой сброса контекста."""
    keyboard = [
        [KeyboardButton(text="Новый диалог 🔄")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


# --- ХЭНДЛЕР ОЧИСТКИ КОНТЕКСТА ---
# Перехватывает команду /clear, /newchat или нажатие на кнопку "Новый диалог 🔄"
@dp.message(F.text.in_({"/clear", "/newchat", "Новый диалог 🔄"}))
async def handle_clear_context(message: Message):
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        await message.answer("💥 Не удалось определить ID пользователя.")
        return

    status_msg = await message.answer("⏳ Сбрасываю контекст диалога...")

    try:
        # Отправляем запрос на эндпоинт очистки контекста в FastAPI
        async with httpx.AsyncClient(timeout=10.0) as client:
            payload = {"user_id": user_id}
            response = await client.post(FASTAPI_CLEAR_URL, json=payload)

        if response.status_code == 200:
            # Удаляем статусное сообщение "Сбрасываю контекст..."
            try:
                await status_msg.delete()
            except Exception:
                pass

            # Отправляем НОВОЕ сообщение с обычной Reply-клавиатурой
            await message.answer(
                "✨ *Контекст успешно сброшен!*\n\n"
                "История нашего диалога за последний час очищена. "
                "Задавай любой новый вопрос!",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard()
            )
        else:
            await status_msg.edit_text(
                f"❌ Ошибка сервера при очистке ({response.status_code}): {response.text[:200]}"
            )
    except Exception as exc:
        logger.error("Ошибка при вызове api/clear-context: {}", exc)
        await status_msg.edit_text(f"💥 Не удалось связаться с сервером для очистки: {exc}")


# --- ОСНОВНОЙ ХЭНДЛЕР ВОПРОСОВ ---
# Игнорирует триггеры очистки контекста, обрабатывает стандартные вопросы
@dp.message(F.text & ~F.text.in_({"/clear", "/newchat", "Новый диалог 🔄"}))
async def handle_text(message: Message):
    status_msg = await message.answer("⏳ Запрос получен, ищу информацию...")

    db_session: Session = get_db_connection()
    db = DBObject(connection=db_session)

    try:
        # Сохраняем вопрос в БД PostgreSQL
        question = db.save_question(
            question_text=message.text,
            user_id=message.from_user.id if message.from_user else None,
        )

        # Отправляем задачу в FastAPI для обработки пайплайна
        async with httpx.AsyncClient(timeout=120.0) as client:
            payload = {
                "message_id": question.id,
                "user_id": question.user_id,
            }
            response = await client.post(FASTAPI_UPDATE_URL, json=payload)

        if response.status_code == 200:
            result = response.json()
            answer = result.get("payload", {}).get("text", "Ответ не получен")

            # Удаляем статусное сообщение "ищу информацию..."
            try:
                await status_msg.delete()
            except Exception:
                pass

            # Отправляем ответ AI НОВЫМ сообщением и прикрепляем Reply-кнопку
            await message.answer(
                f"✅ {answer}",
                parse_mode="MarkdownV2",
                reply_markup=get_main_keyboard()
            )
        else:
            await status_msg.edit_text(
                f"❌ Ошибка сервера ({response.status_code}): {response.text[:500]}"
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