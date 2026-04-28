from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from product_assistant.core.config import settings
from product_assistant.models.schema import Base

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10
)

Connection = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


def get_db_connection() -> Session:
    return Connection()


def init_db():
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
