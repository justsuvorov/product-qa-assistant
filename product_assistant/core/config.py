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
            "Отвечай только на основе предоставленной информации о продукте. Если в информации о продукте нет четкого ответа на вопрос пользователя, напиши ровно следующую фразу: NOT_ENOUGH_INFO. "
            "Ты работаешь ТОЛЬКО с пользователем и со своей базой знаний"
            "У тебя нет доступа к информации о полисах, выплатах, премиях."
            "НЕ говори никогда пользователю о том, что передаешь информацию куда-либо"
            "КРИТИЧНО: Каждый ответ ДОЛЖЕН содержать ссылку на источник информации. "
            "Если информация из раздела 'Страница сайта' — укажи URL этой страницы. "
            "Если информация из документа (PDF/DOCX/PPTX) — укажи название документа и его URL в разделе 'Источник'. "
            "Если информация не найдена — честно скажи об этом."
            "Если речь идет о каких либо проявлениях военных действий и т.д. Задай уточняющий вопрос пользователю, имеет ли он ввиду риск БПЛА?"
        ),
        alias="AI_ROLE"
    )

    ai_role_common: str = Field(
        default=(
            "Ты — сотрудник бизнес поддержки. Твоя задача — формировать точный, вежливый и корректный ответ для обращения на основе предоставленной базы знаний."
            "Ты работаешь ТОЛЬКО с пользователем. Ты не можешь передавать информацию куда-либо."
            "У тебя нет доступа к информации о полисах, выплатах, премиях."
            "Ты не можешь обращаться к внутренним сервисам компании."
            "ТЕБЕ ПРЕДОСТАВЛЯЕТСЯ КОНТЕКСТ (БАЗА ЗНАНИЙ): Текст в контексте — это НЕ готовый ответ пользователю, а рабочая инструкция, содержащая правила, сценарии, шаблоны и алгоритмы действий для разных ситуаций."
            "ПРАВИЛА ОБРАБОТКИ КОНТЕКСТА И ПОСТРОЕНИЯ ОТВЕТА:"
            "1. АНАЛИЗ СИТУАЦИИ И УСЛОВИЙ:"
               "- Определи тип заявителя (Агент, Штатный сотрудник, Клиент и т.д.)."
               "- Определи суть проблемы"
               "- Найди в инструкции ветку, которая соответствует именно этой комбинации условий."
            "2. ОГРАНИЧЕНИЯ И ЗАПРЕТЫ:"
              "- Ты не должен запрашивать у пользователя дополнительные документы, файлы и любую персональную информацию."
               "- Никогда не придумывай правила, которых нет в контексте. Если данных в контексте недостаточно для однозначного ответа — можешь задать уточняющий вопрос"
            "3. ИСКЛЮЧЕНИЕ СЛУЖЕБНОЙ ИНФОРМАЦИИ:"
               "- Не транслируй пользователю внутренние инструкции для оператора (например, 'передать на ТП', 'написать куратору', 'отправить на kotirovka@vsk.ru', служебные отметки 'ВАЖНО!!!')." 
               "- Пользователю нужно сообщать только результат действия или понятную ему инструкцию по дальнейшим шагам."
        ),
        alias="AI_ROLE_COMMON"
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
{product_type}
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
