from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    """Собственный базовый класс от декларативного базового класса ORM.

    Почему это полезно:
    - SQLAlchemy автоматически собирает метаданные всех моделей в Base.metadata.
    - Alembic может использовать Base.metadata для автогенерации миграций.
    - Можно добавлять общие методы/миксины (например timestamps, id и т.д.).
    - Централизованная структура моделей.
    """
    pass