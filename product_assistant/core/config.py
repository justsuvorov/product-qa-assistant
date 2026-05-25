from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr


class Settings(BaseSettings):
    database_url: str = Field(..., alias="DATABASE_URL")

    # AI — Qwen через внутренний OpenAI-compatible API
    qwen_api_url: str = Field("", alias="QWEN_API_URL")
    qwen_model_name: str = Field("Qwen3.6-35B-A3B", alias="QWEN_MODEL_NAME")
    ai_temperature: float = Field(0.3, alias="AI_TEMPERATURE")

    # Telegram
    telegram_bot_token: SecretStr | None = Field(None, alias="TELEGRAM_BOT_TOKEN")

    # Products website to scrape
    products_website_url: str = Field("", alias="PRODUCTS_WEBSITE_URL")

    # "requests" — статический HTML; "playwright" — JS-рендеринг (SPA)
    scraper_type: str = Field("playwright", alias="SCRAPER_TYPE")

    # Явные пути продуктов (через запятую), напр.: /avto/kasko,/avto/osago
    product_paths: str = Field("", alias="PRODUCT_PATHS")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    ai_role: str = (
        "Ты — профессиональный консультант по страховым продуктам. "
        "Отвечай точно и кратко, опираясь только на предоставленную информацию о продукте. "
        "Если ответ есть в тексте — укажи соответствующий пункт. "
        "Если информация не найдена — честно скажи об этом."
    )

    ai_prompt_template: str = """
{role}

### ИНФОРМАЦИЯ О ПРОДУКТЕ:
{product_info}

### ВОПРОС ПОЛЬЗОВАТЕЛЯ:
{question}

### ОТВЕТ:
"""


settings = Settings()
