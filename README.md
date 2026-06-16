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
| LLM | Qwen (внутренний OpenAI-compatible API) |
| База данных | PostgreSQL, SQLAlchemy 2.0 |
| Парсинг сайта | Playwright (SPA) / Requests (статика) — автовыбор |
| Документы | PDF (pymupdf), DOCX (python-docx), PPTX (python-pptx) |
| Логирование | Loguru |
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
  │ QwenModel → ответ LLM                                │
  │   • retry x3 при 503 UNAVAILABLE (пауза 5 сек)      │
  │   • очистка <think>...</think> тегов                 │
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
TELEGRAM_BOT_TOKEN=your_telegram_token

PRODUCTS_WEBSITE_URL=https://your-products-site.ru
SCRAPER_TYPE=auto
PRODUCT_PATHS=/path/to/product1,/path/to/product2

QWEN_API_URL=https://model-1.ai-api.vsk.ru/v1/completions
QWEN_MODEL_NAME=Qwen3.6-35B-A3B
AI_TEMPERATURE=0.3
```

### 2. Docker (рекомендуется)

```bash
docker compose up --build
```

Порядок запуска: `db` → `api` (парсинг сайта при старте) → `bot`

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

## Тесты

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
pytest tests/ --cov=product_assistant  # С покрытием
```

Текущее состояние: **0% покрытия** (тесты не реализованы). 
Смотри [DEVELOPMENT.md](DEVELOPMENT.md#написание-тестов) для примеров тестов.

**Планируемое покрытие:**
- `PostProcessor` — очистка кода, экранирование MarkdownV2
- `TextPreprocessor` — очистка текста, поиск продукта, полный pipeline
- `PromptEngine` — сборка промпта
- `ReportExport` — JSON-ответ, сохранение в БД
- `AIAssistantService` — оркестрирование pipeline
- Scrapers — парсинг страниц, обработка документов
- Edge cases — пустые ответы, ошибки БД, timeout'ы

Целевой показатель: **>70% покрытия** критических путей.

---

## Известные проблемы и план решения

⚠️ **[REFACTORING.md](REFACTORING.md)** содержит подробный план по улучшению проекта.

### Критические (исправить немедленно)
1. **JavaScript синтаксис ошибка** в `product_assistant/scraper/playwright_scraper.py:89`
   - Стоит Cyrillic символ `Но` в JavaScript коде
   - **Влияние:** page.evaluate() падает
   
2. **SSL проверка отключена** в `document_parser.py` и `model.py`
   - **Риск:** MITM атаки в production
   - **Решение:** Включить или задокументировать причину

### Высокий приоритет (рефакторинг)
- **Дублирование кода:** 3 функции `_clean_text()`, 4 реализации `_parse_page()`
- **Привязка к БД:** `TextPreprocessor` напрямую работает с БД (сложно тестировать)
- **Bare except блоки:** 12+ мест где ошибки молча игнорируются
- **Отсутствие тестов:** 0% покрытия

### Рекомендуемая схема рефакторинга
1. **Неделя 1:** Исправить критические ошибки, объединить дублирующийся код
2. **Неделя 2-3:** Отделить БД от бизнес-логики, добавить абстрактные слои
3. **Неделя 3-4:** Написать unit и интеграционные тесты

Смотри [REFACTORING.md](REFACTORING.md) для пошагового плана.

---

## Документация

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — Подробное описание архитектуры, модулей и потока данных
- **[REFACTORING.md](REFACTORING.md)** — План рефакторинга, выявленные проблемы и способы их решения
- **[DEVELOPMENT.md](DEVELOPMENT.md)** — Руководство по разработке, тестированию и стандартам кода

---

## Структура проекта

```
product_assistant/
├── ai/
│   ├── model.py              # QwenModel / GeminiModel (AIModel ABC) + retry логика
│   ├── preprocessor.py       # TextPreprocessor + поиск продукта по словам
│   ├── promt_builders.py     # PromptEngine — сборка промпта
│   ├── postprocessor.py      # Форматирование ответа LLM для Telegram
│   ├── product_mapper.py     # Маппинг синонимов продуктов
│   └── encoders.py           # JSON encoder'ы
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
│   ├── selenium_scraper.py   # Парсер сложных SPA + аутентификация
│   ├── local_files_scraper.py# Парсер локальных файлов
│   ├── document_parser.py    # Извлечение текста: PDF, DOCX, PPTX
│   ├── parser.py             # Утилиты парсинга (BeautifulSoup)
│   └── __init__.py           # Фабрика create_scraper()
└── services/
    └── assistant.py          # AIAssistantService (оркестратор)

main.py                       # FastAPI + lifespan (парсинг при старте)
bot_main.py                   # Telegram-бот (aiogram 3)
product_aliases.json          # Синонимы продуктов
tests/                        # Юнит-тесты (pytest)
docker-compose.yaml
Dockerfile
.env.example
requirements.txt
requirements-dev.txt          # pytest + dev зависимости
```
