from pydantic import BaseModel, Field
from typing import Optional


class APIRequest(BaseModel):
    """
    Схема входящего запроса для обработки голосового сообщения.
    """
    message_id: int = Field(..., description="Уникальный ID сообщения в базе данных")
    user_id: Optional[int] = Field(None, description="ID пользователя (опционально)")
    priority: int = Field(0, description="Приоритет обработки")

    class Config:
        json_schema_extra = {
            "example": {
                "message_id": 42,
                "user_id": 1001,
                "priority": 1
            }
        }
