"""Root conftest: redirect tests to an isolated test database.

This module is loaded by pytest *before* any subdirectory conftest or test
module.  All module-level code here therefore runs before any ``bot.*`` import,
which means the DATABASE_URL override below is picked up by
``bot.config.Settings()`` when it is first instantiated.
"""

import asyncio
import os
import subprocess
from urllib.parse import urlparse, urlunparse

# ── 1. Derive and inject the test DATABASE_URL ────────────────────────────────

_orig_url: str = os.environ.get("DATABASE_URL", "")
if not _orig_url:
    try:
        from dotenv import dotenv_values

        _orig_url = dotenv_values(".env").get("DATABASE_URL", "")
    except Exception:
        pass

if _orig_url:
    _p = urlparse(_orig_url)
    _db = _p.path.lstrip("/")
    if not _db.endswith("_test"):
        os.environ["DATABASE_URL"] = urlunparse(_p._replace(path="/" + _db + "_test"))

# ── 2. Ensure the test database exists and is up-to-date ─────────────────────
#
# This runs synchronously at collection time — before the integration conftest's
# pytest_collection_modifyitems checks whether the DB is reachable.


def _bootstrap_test_db() -> None:
    test_url = os.environ.get("DATABASE_URL", "")
    if not test_url:
        return

    p = urlparse(test_url)
    test_db = p.path.lstrip("/")

    # asyncpg uses "postgresql://" not "postgresql+asyncpg://"
    admin_dsn = urlunparse(
        p._replace(scheme="postgresql", path="/postgres")
    ).replace("postgresql+asyncpg://", "postgresql://")

    async def _create_if_missing() -> None:
        try:
            import asyncpg

            conn = await asyncpg.connect(dsn=admin_dsn)
            try:
                exists = await conn.fetchval(
                    "SELECT 1 FROM pg_database WHERE datname = $1", test_db
                )
                if not exists:
                    await conn.execute(f'CREATE DATABASE "{test_db}"')
            finally:
                await conn.close()
        except Exception:
            # Postgres not available — integration/e2e tests will be skipped
            # by their own collection hooks.
            return

    asyncio.run(_create_if_missing())
    subprocess.run(["alembic", "upgrade", "head"])  # no-op if schema is current


_bootstrap_test_db()
