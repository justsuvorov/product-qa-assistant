import os

# Provide required env vars before any module loads Settings()
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-telegram-token")
