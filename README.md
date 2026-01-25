# Family Costs Bot

[![CI/CD](https://github.com/marmotabobak/family-costs-bot-3/workflows/CI%2FCD/badge.svg)](https://github.com/marmotabobak/family-costs-bot-3/actions)
[![codecov](https://codecov.io/gh/marmotabobak/family-costs-bot-3/branch/master/graph/badge.svg)](https://codecov.io/gh/marmotabobak/family-costs-bot-3)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://www.python.org/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

Telegram-бот для учёта расходов.

## Функциональность

- Пользователи отправляют сообщения с расходами.
- Бот парсит сообщения и сохраняет расходы в БД (PostgreSQL).
- Бот готовит сводные данные по внесенным расходам по запросу Пользователей.
- Web UI для импорта чеков из ВкусВилл. 

### Формат сообщения
```
расход сумма
расход сумма
...
```

Примеры:
```
Продукты 100
вода из Лавки 123.45
корректировка -567.89
```

### Команды
- `/menu` — меню Бота
- `/help` — справка по формату сообщений и работе с Ботом

## Технологии

- Python 3.12
- aiogram 3.x: Telegram Bot API
- FastAPI + Jinja2: Web UI для импорта чеков
- SQLAlchemy 2.x (async): ORM
- asyncpg: async драйвер PostgreSQL
- Alembic: миграции БД
- pytest: тестирование
- ruff + mypy: линтеры
- Docker: контейнеризация
- GitHub Actions: CI/CD

## Структура проекта

```
bot/
├── config.py              # Настройки (Pydantic Settings)
├── constants.py           # Константы сообщений бота
├── exceptions.py          # Кастомные исключения
├── main.py                # Точка входа
├── middleware.py          # FSM middleware
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
│   ├── menu.py            # /menu и inline-кнопки
│   └── messages.py        # Обработчик сообщений
├── services/
│   └── message_parser.py  # Парсинг сообщений
└── web/
    ├── app.py             # FastAPI приложение (импорт чеков)
    ├── static/            # CSS стили
    └── templates/         # Jinja2 шаблоны

tests/
├── conftest.py            # Настройка окружения, safety checks
├── unit/                  # Unit-тесты
│   ├── conftest.py        # Shared fixtures
│   ├── test_*.py          # Тесты модулей
└── integration/           # Интеграционные тесты

migrations/                # Alembic миграции
```

- - - - - - - - - -


## Quick start (локальная разработка)

### 1. Настройка dev-окружения

```bash
# Клонирование репозитория
git clone <repo>
cd <FOLDER_NAME>

# Подготовка виртуального окружения
python -m venv venv
source venv/bin/activate

# Установка зависимостей
make install-dev

# Установка pre-commit хуков
make hooks
```

### 2. Конфигурация

Создайте `.env`:
```env
BOT_TOKEN=<TELEGRAM_BOT_TOKEN>

POSTGRES_USER=test
POSTGRES_PASSWORD=test
POSTGRES_DB=test_db
POSTGRES_PORT=5432

DATABASE_URL=postgresql+asyncpg://test:test@localhost:5432/test_db
ENV=dev
```

### 3. Запуск

```bash
make db        # Запустить БД (PostgreSQL) в контейнере
make migrate   # Применить миграции БД
make bot       # Запустить бота
```

### 4. Web UI для импорта чеков (опционально)

```bash
# Запустить web-сервер
poetry run uvicorn bot.web.app:app --reload --port 8000

# Создать токен для импорта (только в dev-режиме)
# GET http://localhost:8000/dev/create-token/{user_id}
# Затем перейти по ссылке из ответа
```

### Web API Endpoints

| Endpoint | Описание |
|----------|----------|
| `GET /health` | Health check для мониторинга |
| `GET /dev/create-token/{user_id}` | Создать токен (только dev) |
| `GET /import/{token}` | Страница загрузки файла |
| `POST /import/{token}/upload` | Загрузить JSON с чеками |
| `GET /import/{token}/select` | Выбор позиций для сохранения |
| `POST /import/{token}/save` | Сохранить выбранные позиции |


- - - - - - - - - -


## Makefile

### DEV-окружение

| Команда            | Описание                               |
|--------------------|----------------------------------------|
| `make install`     | Установить PROD зависимости            |
| `make install-dev` | Установить DEV зависимости             |
| `make db`          | Запустить БД (PostgreSQL) в контейнере |
| `make bot`         | Запустить бота локально (для DEV)      |

### Docker

| Команда         | Описание                               |
|-----------------|----------------------------------------|
| `make up`       | Запустить все сервисы (postgres + bot) |
| `make down`     | Остановить контейнеры                  |
| `make logs`     | Логи всех контейнеров                  |
| `make logs-bot` | Логи бота                              |
| `make logs-db`  | Логи PostgreSQL                        |

### Миграции БД

| Команда                  | Описание            |
|--------------------------|---------------------|
| `make migrate`           | Применить миграции  |

**Качество кода:**

| Команда           | Описание                            |
|-------------------|-------------------------------------|
| `make lint`       | Запустить ruff + mypy               |
| `make hooks`      | Установить pre-commit хуки          |
| `make pre-commit` | Запустить pre-commit на всех файлах |
| `make test`       | Запустить тесты                     |
| `make cov`        | Тесты с coverage отчётом            |
| `make clean`      | Очистить кэши                       |

## Тестирование

```bash
# Запустить все тесты
make test

# Подготовить отчёт по тестовому покрытия
make test-cov

# Конкретный файл
pytest tests/unit/test_message_parser.py -v
```

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
# Запустить всё в Docker
make up

# Только PostgreSQL (для локальной разработки)
make db

# Просмотр логов
make logs        # все контейнеры
make logs-bot    # только бот
make logs-db     # только postgres
```

## CI/CD (GitHub Actions)

Push в master запрещён (только через PR).

**При push в ветку / PR:**
1. Линтинг (ruff, mypy) на Python 3.10, 3.11, 3.12
2. Тесты с ENV=test (с отчётом по покрытию в Codecov)

**При merge в master:**
3. Автоматический деплой на удалённый хост

### Настройка деплоя

Добавьте секреты в GitHub: Settings → Secrets and variables → Actions:

| Секрет           | Описание                  | Пример                  |
|------------------|---------------------------|-------------------------|
| `DEPLOY_HOST`    | IP или hostname сервера   | `192.168.1.100`         |
| `DEPLOY_USER`    | SSH пользователь          | `deploy`                |
| `DEPLOY_SSH_KEY` | Приватный SSH ключ        | `-----BEGIN OPENSSH...` |
| `DEPLOY_PORT`    | SSH порт (опционально)    | `22`                    |
| `DEPLOY_PATH`    | Путь к проекту на сервере | `/home/deploy/bot`      |

### Первоначальная настройка сервера

```bash
# Клонировать репозиторий
git clone <repo> /home/deploy/bot
cd /home/deploy/bot

# Создать .env с production значениями
cat > .env << EOF
BOT_TOKEN=your-production-token
POSTGRES_USER=prod_user
POSTGRES_PASSWORD=secure_password
POSTGRES_DB=family_costs
POSTGRES_PORT=5432
ENV=prod
EOF

# Запустить
docker-compose up -d --build
```

## Переменная ENV

Переменная `ENV` управляет режимом работы:

| Значение | Описание                                    |
|----------|---------------------------------------------|
| `dev`    | Разработка: SQL-логирование включено        |
| `test`   | Тесты: автоматически устанавливается pytest |
| `prod`   | Production: SQL-логирование выключено       |

Тесты блокируются при `ENV=prod` для защиты production БД.

## TODO
- добавить id бота в модель данных расходов, чтобы разделить данные от пользователя из разных ботов
- собирать URL сервисом самостоятельно (не импортом из env): данные доступны из других env
- тестовый стенд с тестовым ботом

## BUGS
- попытка записи в БД расхода от неавторизованного пользователя
- запись расхода со спецсимволами, например: "тест_2 1" - записывает в БД, но потом ошибка отображения
TelegramBadRequest: Telegram server says - Bad Request: can't parse entities: Can't find end of the entity starting at byte offset 304

## Лицензия

MIT
