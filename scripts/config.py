#!/usr/bin/env python3
"""
Setup scripts for family-costs-bot.

Commands:
  env    — create or validate .env (no DB required)
  admin  — check/create admin user in the database
"""

import asyncio
import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# All keys managed by this script (DATABASE_URL is derived, not prompted directly)
REQUIRED_KEYS = [
    "BOT_TOKEN",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "POSTGRES_PORT",
    "DATABASE_URL",
    "ENV",
    "ADMIN_TELEGRAM_ID",
    "ADMIN_DEFAULT_PASSWORD",
    "WEB_BASE_URL",
    "WEB_PORT",
    "WEB_ROOT_PATH",
]

# label, default, secret
FIELD_META: dict[str, tuple[str, str | None, bool]] = {
    "BOT_TOKEN":              ("Telegram bot token (from @BotFather)", None, True),
    "POSTGRES_USER":          ("PostgreSQL user", "postgres", False),
    "POSTGRES_PASSWORD":      ("PostgreSQL password", None, True),
    "POSTGRES_DB":            ("PostgreSQL database", "family-costs-bot", False),
    "POSTGRES_PORT":          ("PostgreSQL port", "5432", False),
    "ENV":                    ("Environment (dev/prod)", "prod", False),
    "ADMIN_TELEGRAM_ID":      ("Your Telegram numeric ID", None, False),
    "ADMIN_DEFAULT_PASSWORD": ("Password for web UI", None, True),
    "WEB_BASE_URL":           ("WEB_BASE_URL", "http://localhost", False),
    "WEB_PORT":               ("WEB_PORT", "8000", False),
    "WEB_ROOT_PATH":          ("WEB_ROOT_PATH", "/family-costs-bot", False),
}

PG_KEYS = {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "POSTGRES_PORT"}


def ask(label: str, default: str | None = None, secret: bool = False) -> str:
    suffix = f" [{default}]" if default is not None else ""
    prompt_str = f"{label}{suffix}: "
    while True:
        value = (getpass.getpass(prompt_str) if secret else input(prompt_str)).strip()
        if value:
            return value
        if default is not None:
            return default
        print("  This field is required.")


def load_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


def update_env_file(path: Path, updates: dict[str, str]) -> None:
    """Overwrite matching keys in-place; append any not already present."""
    lines = path.read_text().splitlines() if path.exists() else []
    replaced: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                replaced.add(key)
                continue
        new_lines.append(line)
    for key, value in updates.items():
        if key not in replaced:
            new_lines.append(f"{key}={value}")
    path.write_text("\n".join(new_lines) + "\n")


def build_database_url(env: dict[str, str]) -> str:
    user = env.get("POSTGRES_USER", "postgres")
    password = env.get("POSTGRES_PASSWORD", "")
    db = env.get("POSTGRES_DB", "family-costs-bot")
    port = env.get("POSTGRES_PORT", "5432")
    return f"postgresql+asyncpg://{user}:{password}@localhost:{port}/{db}"


# --- DB helpers ---

async def _find_admin(url: str, telegram_id: int) -> bool:
    import asyncpg

    conn = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        return await conn.fetchval("SELECT id FROM users WHERE telegram_id = $1", telegram_id) is not None
    finally:
        await conn.close()


async def _insert_admin(url: str, telegram_id: int, name: str, password_hash: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        await conn.execute(
            "INSERT INTO users (telegram_id, name, role, password_hash) VALUES ($1, $2, 'admin', $3)",
            telegram_id, name, password_hash,
        )
    finally:
        await conn.close()


# --- Commands ---

def cmd_env() -> None:
    env_file = ROOT / ".env"

    if not env_file.exists():
        _create_env(env_file)
    else:
        _validate_env(env_file)


def _create_env(env_file: Path) -> None:
    print("family-costs-bot setup\n")
    env: dict[str, str] = {}

    token = ask("Telegram bot token (from @BotFather)", secret=True)
    while ":" not in token or len(token) < 20:
        print("  Invalid format — expected something like 123456:ABC-DEF...")
        token = ask("Telegram bot token", secret=True)
    env["BOT_TOKEN"] = token

    print()
    env["POSTGRES_USER"] = ask("PostgreSQL user", default="postgres")
    env["POSTGRES_PASSWORD"] = ask("PostgreSQL password", secret=True)
    env["POSTGRES_DB"] = ask("PostgreSQL database", default="family-costs-bot")
    env["POSTGRES_PORT"] = ask("PostgreSQL port", default="5432")
    env["DATABASE_URL"] = build_database_url(env)

    print()
    env["ENV"] = ask("Environment (dev/prod)", default="prod")

    print("\nAdmin account:")
    tid = ask("Your Telegram numeric ID")
    while not tid.lstrip("-").isdigit():
        print("  Must be a number.")
        tid = ask("Your Telegram numeric ID")
    env["ADMIN_TELEGRAM_ID"] = tid
    env["ADMIN_DEFAULT_PASSWORD"] = ask("Password for web UI", secret=True)

    print()
    env["WEB_BASE_URL"] = ask("WEB_BASE_URL", default="http://localhost")
    env["WEB_PORT"] = ask("WEB_PORT", default="8000")
    env["WEB_ROOT_PATH"] = ask("WEB_ROOT_PATH", default="/family-costs-bot")

    env_file.write_text(
        f"BOT_TOKEN={env['BOT_TOKEN']}\n"
        f"\n"
        f"POSTGRES_USER={env['POSTGRES_USER']}\n"
        f"POSTGRES_PASSWORD={env['POSTGRES_PASSWORD']}\n"
        f"POSTGRES_DB={env['POSTGRES_DB']}\n"
        f"POSTGRES_PORT={env['POSTGRES_PORT']}\n"
        f"DATABASE_URL={env['DATABASE_URL']}\n"
        f"\n"
        f"ENV={env['ENV']}\n"
        f"\n"
        f"ADMIN_TELEGRAM_ID={env['ADMIN_TELEGRAM_ID']}\n"
        f"ADMIN_DEFAULT_PASSWORD={env['ADMIN_DEFAULT_PASSWORD']}\n"
        f"\n"
        f"WEB_BASE_URL={env['WEB_BASE_URL']}\n"
        f"WEB_PORT={env['WEB_PORT']}\n"
        f"WEB_ROOT_PATH={env['WEB_ROOT_PATH']}\n"
    )
    print("\n.env written. Next: make up && make admin")


def _validate_env(env_file: Path) -> None:
    env = load_env(env_file)
    missing = [k for k in REQUIRED_KEYS if not env.get(k)]

    if not missing:
        print(".env is complete.")
        return

    print(f"Missing required values: {', '.join(missing)}\n")
    new_values: dict[str, str] = {}
    pg_touched = False

    for key in missing:
        if key == "DATABASE_URL":
            continue
        label, default, secret = FIELD_META[key]
        new_values[key] = ask(f"  {label}", default=default, secret=secret)
        if key in PG_KEYS:
            pg_touched = True

    if pg_touched or "DATABASE_URL" in missing:
        merged = {**env, **new_values}
        new_values["DATABASE_URL"] = build_database_url(merged)

    update_env_file(env_file, new_values)
    print("\n.env updated.")


def cmd_admin() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        print(".env not found. Run `make env` first.")
        sys.exit(1)

    env = load_env(env_file)
    database_url = env.get("DATABASE_URL")
    tid_str = env.get("ADMIN_TELEGRAM_ID")

    if not database_url:
        print("DATABASE_URL not set in .env. Run `make env` to fix.")
        sys.exit(1)
    if not tid_str or not tid_str.lstrip("-").isdigit():
        print("ADMIN_TELEGRAM_ID is missing or invalid in .env. Run `make env` to fix.")
        sys.exit(1)

    telegram_id = int(tid_str)
    print(f"Checking admin user (telegram_id={telegram_id})...")

    try:
        found = asyncio.run(_find_admin(database_url, telegram_id))
    except Exception as e:
        print(f"Could not connect to database: {e}")
        print("Make sure services are running (make up) and migrations are applied.")
        sys.exit(1)

    if found:
        print("Admin user exists.")
        return

    print("Admin user not found.")
    answer = input("Create admin user now? [Y/n]: ").strip().lower()
    if answer not in ("", "y", "yes"):
        return

    import bcrypt

    name = ask("Display name", default="Admin")
    default_password = env.get("ADMIN_DEFAULT_PASSWORD") or None
    password = ask("Password for web UI", default=default_password, secret=True)
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    try:
        asyncio.run(_insert_admin(database_url, telegram_id, name, password_hash))
        print(f"Admin '{name}' created.")
    except Exception as e:
        print(f"Failed: {e}")
        sys.exit(1)


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else None
    if cmd == "env":
        cmd_env()
    elif cmd == "admin":
        cmd_admin()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
