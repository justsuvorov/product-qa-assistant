import pytest
from fastapi.testclient import TestClient


# 1. Фикстура автоматически глушит парсинг при старте приложения.
# Мокаем функцию _run_scraping прямо в модуле main ДО инициализации TestClient.
@pytest.fixture(autouse=True)
def mock_lifespan_scraping(mocker):
    return mocker.patch("main._run_scraping", return_value=None)


def test_api_update_end_to_end(mocker):
    # Импортируем app только внутри теста, когда фикстура mock_lifespan_scraping уже активна
    from main import app
    client = TestClient(app)

    # 2. Мокаем метод result() у класса AIAssistantService, чтобы полностью
    # изолировать тест от реальной базы данных и запросов к Gemini API.
    # Это позволяет проверить весь сквозной проход запроса через FastAPI.
    fake_response = {
        "message_id": 42,
        "status": "success",
        "db_status": "saved",
        "payload": {
            "text": "Да, входит. Указано в пункте 3.1 'Полная гибель (тоталь)'",
            "format": "telegram_markdown"
        }
    }

    mock_assistant = mocker.patch(
        "product_assistant.services.assistant.AIAssistantService.result",
        return_value=fake_response
    )

    # Также мокаем соединение с БД внутри самого эндпоинта, чтобы тест не упал на get_db_connection()
    mocker.patch("main.get_db_connection")
    mocker.patch("main.DBObject")

    # 3. Отправляем тестовый запрос, имитируя APIRequest
    payload = {
        "message_id": 42,
        "user_id": 12345
    }
    response = client.post("/api/update", json=payload)

    # 4. Проверяем, что API вернуло статус 200 и корректную структуру JSON
    assert response.status_code == 200

    json_data = response.json()
    assert json_data["status"] == "success"
    assert json_data["db_status"] == "saved"
    assert json_data["payload"]["format"] == "telegram_markdown"
    assert "пункте 3.1" in json_data["payload"]["text"]

    # Проверяем, что наш ИИ-сервис действительно вызывался бэкендом
    mock_assistant.assert_called_once()