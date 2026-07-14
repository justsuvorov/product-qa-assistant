from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr


class Settings(BaseSettings):
    database_url: str = Field(..., alias="DATABASE_URL")

    # AI — Qwen через внутренний OpenAI-compatible API
    qwen_api_url: str = Field("", alias="QWEN_API_URL")
    qwen_model_name: str = Field("Qwen3.6-35B-A3B", alias="QWEN_MODEL_NAME")
    qwen_max_tokens: int = Field(100000, alias="QWEN_MAX_TOKENS")
    ai_temperature: float = Field(0.3, alias="AI_TEMPERATURE")

    gemini_api_key: SecretStr = Field(..., alias="GEMINI_API_KEY")
    model_name: str = Field("gemini-3.1-flash-lite", alias="AI_MODEL_NAME")
    # Telegram
    telegram_bot_token: SecretStr | None = Field(None, alias="TELEGRAM_BOT_TOKEN")

    # Products website to scrape
    products_website_url: str = Field("", alias="PRODUCTS_WEBSITE_URL")

    # "requests" — статический HTML; "playwright" — JS-рендеринг (SPA)
    scraper_type: str = Field("playwright", alias="SCRAPER_TYPE")

    # Явные пути продуктов (через запятую), напр.: /avto/kasko,/avto/osago
    product_paths: str = Field("", alias="PRODUCT_PATHS")

    # Путь до JSON-файла со словарём алиасов продуктов
    product_aliases_path: str = Field("product_aliases.json", alias="PRODUCT_ALIASES_PATH")

    # Selenium Grid URL (если пусто — используется локальный Chrome)
    selenium_url: str = Field("", alias="SELENIUM_URL")

    # Авторизация на сайте продуктов (Keycloak)
    scraper_username: str = Field("", alias="SCRAPER_USERNAME")
    scraper_password: str = Field("", alias="SCRAPER_PASSWORD")

    # Директория с локальными документами (для SCRAPER_TYPE=local_files)
    local_files_dir: str = Field("", alias="LOCAL_FILES_DIR")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    ai_role: str = Field(
        default=(
            "Ты — профессиональный консультант по страховым продуктам. "
            "Отвечай точно и кратко, опираясь только на предоставленную информацию о продукте. "
            "КРИТИЧНО: Каждый ответ ДОЛЖЕН содержать ссылку на источник информации. "
            "Если информация из раздела 'Страница сайта' — укажи URL этой страницы. "
            "Если информация из документа (PDF/DOCX/PPTX) — укажи название документа и его URL в разделе 'Источник'. "
            "Если информация не найдена — честно скажи об этом."
        ),
        alias="AI_ROLE"
    )

    ai_list_request_role: str = Field(
        default=(
            "Ты — консультант по страховым продуктам. "
            "Пользователь спрашивает какие услуги ты можешь предложить. "
            "Предоставь обзор всех доступных продуктов в естественной, компактной и привлекательной форме."
        ),
        alias="AI_LIST_REQUEST_ROLE"
    )

    ai_prompt_template: str = Field(
        default="""
{role}

### ИНФОРМАЦИЯ О ПРОДУКТЕ:
{product_info}

### ИСТОРИЯ ДИАЛОГА:
{context}

### ВОПРОС ПОЛЬЗОВАТЕЛЯ:
{question}

### ИНСТРУКЦИИ ДЛЯ ОТВЕТА:
1. Ответь на вопрос, основываясь на информации выше
2. Обязательно укажи URL источника информации в формате: Источник: [URL]
3. Если информация из раздела "Страница сайта" — используй указанный там URL
4. Если информация из документа — используй URL из раздела "Источник:" документа
5. Ответ должен быть точным, кратким и содержать ссылку на источник

### ОТВЕТ:
""",
        alias="AI_PROMPT_TEMPLATE"
    )


settings = Settings()
