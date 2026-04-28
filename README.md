# Product QA Assistant

Микросервис для ответов на вопросы по продуктам на базе FastAPI + LLM.
Пользователь задаёт вопрос через Telegram-бота (или любой другой текстовый интерфейс),
приложение находит нужный продукт в базе и возвращает точный ответ со ссылкой на пункт документации.

**Пример:**
> Вопрос: «Входит ли в КАСКО Страхование Классика покрытие тоталя?»
> Ответ: «Да, входит. Указано в пункте 3.1 "Полная гибель (тоталь)"»

---

## Технический стек

| Компонент | Технология |
|-----------|-----------|
| API | Python 3.10+, FastAPI |
| LLM | Google Gemini 1.5 Flash (заменяется на любую модель) |
| База данных | PostgreSQL, SQLAlchemy 2.0 |
| Парсинг сайта | BeautifulSoup4, Requests |
| Telegram Bot | aiogram 3 |

---

## Архитектура

```
Пользователь (Telegram / любой UI)
        │ текстовый вопрос
        ▼
   bot_main.py
  ┌─────────────────────────────────────┐
  │ 1. Сохраняет вопрос в user_questions│
  │ 2. POST /api/update {message_id}    │
  └──────────────┬──────────────────────┘
                 │
        ▼
   main.py (FastAPI)
  ┌─────────────────────────────────────────────────────┐
  │ TextPreprocessor                                     │
  │   • очистка текста                                   │
  │   • поиск продукта в таблице products (по словам)    │
  │   • сборка промпта: роль + контент продукта + вопрос │
  ├─────────────────────────────────────────────────────┤
  │ GeminiModel → ответ LLM                              │
  ├─────────────────────────────────────────────────────┤
  │ PostProcessor → форматирование для Telegram          │
  ├─────────────────────────────────────────────────────┤
  │ ReportExport → сохранение результата в БД            │
  └──────────────┬──────────────────────────────────────┘
                 │ JSON {payload.text}
        ▼
   bot_main.py → отправляет ответ пользователю
```

### Инициализация (при старте приложения)

```
FastAPI lifespan
  → ProductScraper.scrape_all()
      → обходит PRODUCTS_WEBSITE_URL
      → парсит страницы продуктов (BeautifulSoup)
      → upsert в таблицу products
```

---

## Таблицы БД

### `products`
| Поле | Описание |
|------|----------|
| `id` | PK |
| `name` | Название продукта |
| `url` | URL страницы продукта |
| `content` | Полный текст страницы |
| `scraped_at` | Дата последнего парсинга |

### `user_questions`
| Поле | Описание |
|------|----------|
| `id` | PK |
| `user_id` | ID пользователя Telegram (опц.) |
| `question_text` | Оригинальный вопрос |
| `cleaned_text` | Очищенный текст |
| `product_id` | FK → products |
| `result_text` | Ответ LLM |
| `created_at` | Время создания |

---

## API

### `POST /api/update`

**Request:**
```json
{ "message_id": 42 }
```

**Response:**
```json
{
  "message_id": 42,
  "status": "success",
  "db_status": "saved",
  "payload": {
    "text": "Да, входит. Указано в пункте 3.1...",
    "format": "telegram_markdown"
  }
}
```

---

## Настройка и запуск

### 1. Переменные окружения

Скопируйте `.env.example` в `.env` и заполните:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/product_qa
GEMINI_API_KEY=your_gemini_key
TELEGRAM_BOT_TOKEN=your_telegram_token
PRODUCTS_WEBSITE_URL=https://your-products-site.ru

# Опционально
AI_MODEL_NAME=gemini-1.5-flash
AI_TEMPERATURE=0.3
```

### 2. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 3. Запуск FastAPI

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

При старте автоматически:
- создаются таблицы в БД
- запускается парсинг сайта продуктов

### 4. Запуск Telegram-бота

```bash
python bot_main.py
```

---

## Адаптация парсера

Парсер в [product_assistant/scraper/parser.py](product_assistant/scraper/parser.py) использует
универсальные CSS-селекторы. Если структура вашего сайта нестандартная — адаптируйте два метода:

- `_collect_product_links()` — логика сбора ссылок на продукты с главной страницы
- `_parse_product_page()` — извлечение названия и текста из страницы продукта

---

## Структура проекта

```
product_assistant/
├── ai/
│   ├── model.py           # GeminiModel (AIModel ABC)
│   ├── preprocessor.py    # TextPreprocessor + поиск продукта
│   ├── promt_builders.py  # PromptEngine
│   └── postprocessor.py   # Форматирование ответа LLM
├── core/
│   ├── config.py          # Settings (pydantic-settings)
│   └── database.py        # SQLAlchemy engine + init_db
├── models/
│   ├── request.py         # APIRequest (Pydantic)
│   └── schema.py          # ORM: Product, UserQuestion, DBObject
├── reports/
│   └── report_export.py   # Сохранение результата + формирование JSON
├── scraper/
│   └── parser.py          # ProductScraper (BeautifulSoup)
└── services/
    └── assistant.py       # AIAssistantService (оркестратор)
main.py                    # FastAPI + lifespan
bot_main.py                # Telegram-бот (aiogram 3)
requirements.txt
```
