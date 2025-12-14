# Family Costs Bot 3

Telegram-бот для записи пользовательских сообщений в базу данных.  
Проект использует асинхронный стек Python, PostgreSQL, SQLAlchemy, Alembic и CI/CD на GitHub Actions.

## Технологии

- Python 3.10+
- aiogram 3.x — работа с Telegram Bot API
- SQLAlchemy 2.x (async) — ORM и работа с БД
- asyncpg — драйвер PostgreSQL
- Alembic — миграции базы данных
- pytest + pytest-asyncio — тесты
- ruff + mypy — статический анализ и линтинг
- Docker + docker-compose — локальная инфраструктура
- GitHub Actions — CI с тестами, линтерами и покрытием

## Структура проекта

```
bot/
├── config.py              # Настройки приложения (Pydantic Settings)
├── main.py                # Точка входа бота
├── db/
│   ├── base.py            # Declarative Base
│   ├── models.py          # SQLAlchemy модели
│   ├── session.py         # async engine + sessionmaker
│   ├── dependencies.py    # Контекстный менеджер для выдачи сессий
│   └── repositories/
│       └── messages.py    # Работа с сущностью Message
├── handlers/              # Telegram handlers (разрабатывается)
└── services/              # Сервисный слой (разрабатывается)

migrations/
├── env.py                 # Конфигурация Alembic (async)
└── versions/              # Файлы миграций

docker-compose.yml         # Локальный PostgreSQL
alembic.ini                # Конфигурация Alembic
pytest.ini                 # Конфигурация тестов
requirements.txt
requirements-dev.txt
```

## Настройки (.env)

Создайте файл `.env`:

```
# Telegram
BOT_TOKEN=0000000000:example-token

# PostgreSQL
POSTGRES_USER=test
POSTGRES_PASSWORD=test
POSTGRES_DB=test_db
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# SQLAlchemy URLs
DATABASE_URL=postgresql+asyncpg://test:test@localhost:5432/test_db
TEST_DATABASE_URL=postgresql+asyncpg://test:test@localhost:5432/test_db_test

# Environment
ENV=dev
```

## Локальный запуск через Docker

```bash
docker-compose up -d
```

Проверка:

```bash
docker exec -it bot_postgres psql -U test -d test_db
```

## Миграции Alembic

```bash
alembic revision --autogenerate -m "create messages table"
alembic upgrade head
alembic downgrade -1
```

## Запуск приложения

```bash
python -m bot.main
```

## Тестирование

```bash
pytest -vv
pytest --cov=bot --cov-report=term --cov-report=html
```

## CI (GitHub Actions)

При каждом push / pull request в ветку `master`:

- установка зависимостей  
- запуск линтеров (ruff, mypy)  
- поднятие PostgreSQL  
- применение миграций Alembic  
- запуск тестов  
- генерация coverage report  

Файл workflow:

```
.github/workflows/tests.yml
```

## Требования

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## Лицензия

MIT

## TODO:
- склонения (расход/а/ов и др.)

