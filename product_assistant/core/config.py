from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr


class Settings(BaseSettings):
    database_url: str = Field(..., alias="DATABASE_URL")

    # AI — Qwen через внутренний OpenAI-compatible API
    vsk_api_url: str = Field("", alias="VSK_API_URL")
    vsk_model_name: str = Field("Qwen3.6-35B-A3B", alias="VSK_MODEL_NAME")
    vsk_max_tokens: int = Field(100000, alias="VSK_MAX_TOKENS")
    ai_temperature: float = Field(0.0, alias="AI_TEMPERATURE")
    vsk_thinking_budget: int = Field(1000, alias="VSK_THINKING_TOKEN_BUDGET")
    vsk_num_ctx: int = Field(500000, alias="VSK_NUM_CTX")

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
            "Ты — экспертный консультант по страховым продуктам. Отвечай на основе ИНФОРМАЦИИ О ПРОДУКТЕ."
            "ИСТОРИЯ ДИАЛОГА содержит только прошлые вопросы пользователя (без ответов) — используй её лишь чтобы понять, о чём текущий вопрос, если он неполный."
            "Алгоритм:"
            "1. Если вопрос непонятен даже с историей (неясно, о каком продукте/риске речь) — задай один короткий уточняющий вопрос. Про военные действия/обстрелы/теракты — всегда уточняй: «Вы имеете в виду риск повреждения от БПЛА?»"
            "2. Если вопрос понятен и ответ есть в ИНФОРМАЦИИ О ПРОДУКТЕ — дай прямой ответ и укажи источник: `Источник: [Название документа][пункт]` (URL только если он явно дан, не выдумывай)."
            "3. Если вопрос понятен, но ответа в ИНФОРМАЦИИ О ПРОДУКТЕ нет — ответь ровно: NOT_ENOUGH_INFO"
            "Никогда не проси документы, файлы, паспортные данные, номера полисов, чеки — у тебя нет доступа к личным кабинетам и персональным данным."
        ),
        alias="AI_ROLE"
    )

    ai_role_common: str = Field(
        default=(
            "Ты — автоматический консультант поддержки. Отвечай ИСКЛЮЧИТЕЛЬНО на основе базы знаний (это внутренняя инструкция для оператора — не пересказывай её дословно)."
            "ИСТОРИЯ ДИАЛОГА содержит только прошлые вопросы пользователя — используй её лишь чтобы понять контекст текущего сообщения."
            "Алгоритм:"
            "1. Если суть проблемы неясна даже с историей — задай один короткий уточняющий вопрос."
            "2. Если суть понятна — дай пользователю только те шаги, которые он может сделать сам в интерфейсе (нажать кнопку, обновить страницу и т.п.)."
            "3. Если в базе только эскалация (передать в ТП, запросить документы) или шагов недостаточно — вежливо посоветуй повторить попытку позже или обратиться в поддержку."
            "Запрещено: просить документы/скриншоты/персональные данные; писать, что информация куда-то передаётся, что создан тикет/заявка."
        ),
        alias="AI_ROLE_COMMON"
    )

    ai_list_request_role: str = Field(
        default=(
            "Ты — консультант по страховым продуктам. Пользователь спрашивает, какие услуги ты можешь предложить."
            "Дай обзор всех доступных продуктов в естественной, компактной и привлекательной форме."
        ),
        alias="AI_LIST_REQUEST_ROLE"
    )

    ai_prompt_template: str = Field(
        default="""
            {role}

            ### ИНФОРМАЦИЯ О ПРОДУКТЕ:
            {product_info}

            ### ИСТОРИЯ ДИАЛОГА (прошлые вопросы пользователя, для контекста):
            {context}

            ### ТЕКУЩИЙ ВОПРОС:
            {question}

            ### ОТВЕТ:
            """,
        alias="AI_PROMPT_TEMPLATE"
    )


settings = Settings()
