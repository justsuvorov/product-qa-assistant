from datetime import datetime
from sqlalchemy import select, Text, String, Integer, update, DateTime, ForeignKey, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session


class Base(DeclarativeBase):
    pass


class Product(Base):
    """Продукт, спарсенный с сайта."""
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(String(1000), unique=True)
    content: Mapped[str] = mapped_column(Text)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class UserQuestion(Base):
    """Вопрос пользователя."""
    __tablename__ = "user_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=True)
    question_text: Mapped[str] = mapped_column(Text)
    cleaned_text: Mapped[str] = mapped_column(Text, nullable=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"), nullable=True)
    result_text: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class DBObject:
    def __init__(self, connection: Session):
        self.connection = connection

    def save_question(self, question_text: str, user_id: int | None = None) -> UserQuestion:
        question = UserQuestion(question_text=question_text, user_id=user_id)
        self.connection.add(question)
        self.connection.commit()
        self.connection.refresh(question)
        return question

    def get_question(self, message_id: int) -> UserQuestion:
        result = self.connection.execute(
            select(UserQuestion).where(UserQuestion.id == message_id)
        ).scalar_one_or_none()
        if not result:
            raise ValueError(f"Вопрос с id={message_id} не найден")
        return result

    def update_result(self, message_id: int, result_text: str, product_id: int | None = None):
        stmt = (
            update(UserQuestion)
            .where(UserQuestion.id == message_id)
            .values(result_text=result_text, product_id=product_id)
        )
        self.connection.execute(stmt)
        self.connection.commit()

    def upsert_product(self, name: str, url: str, content: str) -> Product:
        """Создаёт или обновляет продукт по URL."""
        existing = self.connection.execute(
            select(Product).where(Product.url == url)
        ).scalar_one_or_none()

        if existing:
            existing.name = name
            existing.content = content
            existing.scraped_at = datetime.utcnow()
            self.connection.commit()
            return existing

        product = Product(name=name, url=url, content=content)
        self.connection.add(product)
        self.connection.commit()
        self.connection.refresh(product)
        return product

    def get_all_products(self) -> list[Product]:
        return self.connection.execute(select(Product)).scalars().all()

    def close(self):
        self.connection.close()

    def __del__(self):
        self.close()
