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
| API | Python 3.11+, FastAPI |
| LLM | Google Gemini (любая модель через `AI_MODEL_NAME`) |
| База данных | PostgreSQL, SQLAlchemy 2.0 |
| Парсинг сайта | Playwright (SPA) / Requests (статика) — автовыбор |
| Документы | PDF (pymupdf), DOCX (python-docx), PPTX (python-pptx) |
| Логирование | Loguru |
| Telegram Bot | aiogram 3 |
| Прокси | Shadowsocks (SOCKS5) |

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
  │   • retry x3 при 503 UNAVAILABLE (пауза 5 сек)      │
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
  → ScraperDetector.detect(url)          # авто: requests или playwright
  → Scraper.scrape_all()
      → для каждой страницы продукта:
          • HTML-текст страницы
          • вкладки/виджеты (те же URL с ?param=...)
          • документы: PDF, DOCX, PPTX
      → upsert в таблицу products
```

---

## Парсер сайта

### Типы парсеров

| Тип | Когда использовать |
|-----|--------------------|
| `requests` | Статический HTML (WordPress, Django, 1C-Bitrix) |
| `playwright` | SPA с JS-рендерингом (React, Vue, Next.js) |
| `auto` | Автоопределение по структуре страницы (рекомендуется) |

**Детектор** (`scraper/detector.py`) анализирует:
- Наличие `<div id="root|app|__next">` — SPA-маркеры
- Webpack/Vite bundle-скрипты (`chunk.abc123.js`)
- Объём текста в ответе (< 300 символов → JS-рендеринг)

### Парсинг документов

Playwright-парсер автоматически находит и обрабатывает вложенные документы:

| Формат | Библиотека | Что извлекается |
|--------|-----------|-----------------|
| PDF | pymupdf | Весь текст постранично |
| DOCX | python-docx | Параграфы + таблицы |
| PPTX | python-pptx | Текст по слайдам |

### Парсинг вкладок / виджетов

Если сайт использует query-параметры для переключения контента
(например `?t=qa`, `?t=insuranceCase`), парсер автоматически обходит все такие
ссылки на той же странице и добавляет их текст к продукту.

---

## Таблицы БД

### `products`
| Поле | Описание |
|------|----------|
| `id` | PK |
| `name` | Название продукта |
| `url` | URL страницы продукта |
| `content` | Текст страницы + вкладки + документы |
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
DATABASE_URL=postgresql://user:password@db:5432/product_assistant
GEMINI_API_KEY=your_gemini_key
TELEGRAM_BOT_TOKEN=your_telegram_token

PRODUCTS_WEBSITE_URL=https://your-products-site.ru
SCRAPER_TYPE=auto
PRODUCT_PATHS=/path/to/product1,/path/to/product2

AI_MODEL_NAME=gemini-2.0-flash
AI_TEMPERATURE=0.3

# Прокси (если Gemini/Telegram недоступны напрямую)
HTTP_PROXY=socks5://ss-client:1080
HTTPS_PROXY=socks5://ss-client:1080
PROXY_URL=socks5://ss-client:1080
SS_ADDRESS=your.ss.server.com
SS_PORT=9000
SS_PASSWORD=your_password
```

### 2. Docker (рекомендуется)

```bash
# Сборка и запуск (прокси нужен только для pull образов)
$env:HTTPS_PROXY = ""; $env:HTTP_PROXY = ""; docker compose up --build
```

Порядок запуска: `db` + `ss-client` → `api` (парсинг сайта) → `bot`

### 3. Локальный запуск

```bash
pip install -r requirements.txt
playwright install chromium   # если SCRAPER_TYPE=playwright или auto

uvicorn main:app --host 0.0.0.0 --port 8000
python bot_main.py
```

### 4. Просмотр данных в БД

```bash
docker exec -it product_qa_db psql -U postgres -d product_assistant
```

```sql
-- Спарсенные продукты
SELECT id, name, url, scraped_at FROM products;

-- Вопросы и ответы
SELECT q.question_text, p.name AS product, q.result_text
FROM user_questions q
LEFT JOIN products p ON q.product_id = p.id
ORDER BY q.created_at DESC LIMIT 10;
```

---

## Структура проекта

```
product_assistant/
├── ai/
│   ├── model.py              # GeminiModel (AIModel ABC) + retry логика
│   ├── preprocessor.py       # TextPreprocessor + поиск продукта по словам
│   ├── promt_builders.py     # PromptEngine
│   └── postprocessor.py      # Форматирование ответа LLM
├── core/
│   ├── config.py             # Settings (pydantic-settings, .env)
│   └── database.py           # SQLAlchemy engine + init_db
├── models/
│   ├── request.py            # APIRequest (Pydantic)
│   └── schema.py             # ORM: Product, UserQuestion, DBObject
├── reports/
│   └── report_export.py      # Сохранение результата + JSON-ответ
├── scraper/
│   ├── base.py               # BaseScraper (ABC) + утилиты
│   ├── detector.py           # ScraperDetector — авто выбор типа парсера
│   ├── requests_scraper.py   # Парсер статических сайтов
│   ├── playwright_scraper.py # Парсер SPA + вкладки + документы
│   ├── document_parser.py    # Извлечение текста: PDF, DOCX, PPTX
│   └── __init__.py           # Фабрика create_scraper()
└── services/
    └── assistant.py          # AIAssistantService (оркестратор)
main.py                       # FastAPI + lifespan (парсинг при старте)
bot_main.py                   # Telegram-бот (aiogram 3, F.text)
Dockerfile
docker-compose.yaml
.env.example
requirements.txt
```
