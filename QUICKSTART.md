# Quickstart

## Prerequisites

- Python 3.11+
- Docker (for PostgreSQL)
- A Telegram bot token — create one via [@BotFather](https://t.me/BotFather)

## 1. Install dependencies

```bash
make install-dev
```

## 2. Create `.env`

```bash
make env
```

Prompts for all required values and writes `.env`. You will be asked for:

- **Telegram bot token** — from [@BotFather](https://t.me/BotFather)
- **PostgreSQL** — user, password, database name (default: `family-costs-bot`), port (default: `5432`)
- **Environment** — `dev` or `prod` (default: `prod`)
- **Admin account** — your Telegram numeric ID and a password for the web UI
- **Web** — `WEB_BASE_URL` (default: `http://localhost`), `WEB_PORT` (default: `8000`), `WEB_ROOT_PATH` (default: `/family-costs-bot`)

If `.env` already exists, `make env` checks for missing fields and prompts only for those.

## 3. Start all services

```bash
make up
make logs   # follow logs
```

## 4. Create admin user

```bash
make admin
```

Checks whether the admin user (identified by `ADMIN_TELEGRAM_ID`) exists in the database. If not, offers to create it interactively.

The web UI will be available at `http://localhost:<WEB_PORT><WEB_ROOT_PATH>` (e.g. `http://localhost:8000/family-costs-bot`).
