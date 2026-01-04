# Family Costs Bot

Telegram-бот для учёта семейных расходов. Пользователи отправляют сообщения с расходами, бот парсит их и сохраняет в PostgreSQL.

## Функциональность

Формат сообщения:
```
расход сумма
расход сумма
...
```

Примеры:
```
Продукты 100
вода из Лавки 123.56
корректировка -500.24
```

Команды:
- `/start` — приветствие и справка
- `/help` — справка по формату сообщений

## Технологии

- Python 3.12
- aiogram 3.x — Telegram Bot API
- SQLAlchemy 2.x (async) — ORM
- asyncpg — драйвер PostgreSQL
- Alembic — миграции БД
- pytest — тесты (99% coverage)
- ruff + mypy — линтинг
- pre-commit — хуки
- Docker — контейнеризация
- GitHub Actions — CI/CD

## Структура проекта

```
bot/
├── config.py              # Настройки (Pydantic Settings)
├── constants.py           # Константы сообщений бота
├── main.py                # Точка входа
├── utils.py               # Утилиты (pluralize)
├── logging_config.py      # Настройка логирования
├── db/
│   ├── base.py            # Declarative Base
│   ├── models.py          # SQLAlchemy модели
│   ├── session.py         # async engine + sessionmaker
│   ├── dependencies.py    # Контекстный менеджер сессий
│   └── repositories/
│       └── messages.py    # Репозиторий Message
├── routers/
│   ├── common.py          # /start, /help handlers
│   └── messages.py        # Обработчик сообщений
└── services/
    └── message_parser.py  # Парсинг сообщений

tests/
├── unit/                  # Unit-тесты (45 тестов)
│   ├── conftest.py        # Shared fixtures
│   ├── test_*.py          # Тесты модулей
└── integration/           # Интеграционные тесты

migrations/                # Alembic миграции
```

## Быстрый старт

### 1. Настройка окружения

```bash
# Клонирование
git clone <repo>
cd family-costs-bot-3

# Виртуальное окружение
python -m venv venv
source venv/bin/activate

# Зависимости
make deps-dev

# Pre-commit хуки
make hooks
```

### 2. Конфигурация

Создайте `.env`:
```env
BOT_TOKEN=your-telegram-bot-token

POSTGRES_USER=test
POSTGRES_PASSWORD=test
POSTGRES_DB=test_db
POSTGRES_PORT=5432

DATABASE_URL=postgresql+asyncpg://test:test@localhost:5432/test_db
ENV=dev
```

### 3. Запуск

**Локально:**
```bash
make up        # Запустить PostgreSQL
make migrate   # Применить миграции
make run       # Запустить бота
```

**Docker:**
```bash
docker-compose up --build
```

## Makefile команды

| Команда | Описание |
|---------|----------|
| `make deps` | Установить production зависимости |
| `make deps-dev` | Установить все зависимости |
| `make up` | Запустить PostgreSQL |
| `make down` | Остановить контейнеры |
| `make migrate` | Применить миграции |
| `make migration m="msg"` | Создать миграцию |
| `make lint` | Запустить ruff + mypy |
| `make hooks` | Установить pre-commit хуки |
| `make pre-commit` | Запустить pre-commit на всех файлах |
| `make test` | Запустить тесты |
| `make cov` | Тесты с coverage отчётом |
| `make run` | Запустить бота |
| `make clean` | Очистить кэши |

## Тестирование

```bash
# Все тесты
make test

# С coverage
make cov

# Конкретный файл
pytest tests/unit/test_message_parser.py -v
```

**Coverage: 99%** (45 тестов)

## Pre-commit хуки

Автоматически запускаются при коммите:
- `trailing-whitespace` — удаление пробелов
- `end-of-file-fixer` — newline в конце файлов
- `check-yaml` — валидация YAML
- `ruff` — линтинг + автоисправление
- `ruff-format` — форматирование
- `mypy` — проверка типов

## Docker

**Dockerfile** — образ на базе Python 3.12-slim

**docker-compose.yml:**
- `postgres` — PostgreSQL 14 с healthcheck
- `bot` — бот (ждёт готовности postgres)

```bash
# Собрать и запустить всё
docker-compose up --build

# Только PostgreSQL (для локальной разработки)
docker-compose up postgres
```

## CI/CD (GitHub Actions)

При push/PR в `master`:
1. Линтинг (ruff, mypy) на Python 3.10, 3.11
2. Тесты с PostgreSQL
3. Coverage отчёт

## Лицензия

MIT
