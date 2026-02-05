"""Root conftest - safety checks and test environment setup.

Must live at the project root (next to pyproject.toml) so that
pytest_configure runs *before* any tests/…/conftest.py is imported.
Otherwise subdirectory conftest imports can trigger bot.config.Settings()
while os.environ["ENV"] is still unset, locking in ENV=dev from .env.
"""

import os

import pytest


def pytest_configure(config):
    """Prevent running tests against production environment."""
    # Check BEFORE overriding - catch attempts to run tests on prod
    original_env = os.environ.get("ENV", "")
    if original_env == "prod":
        pytest.exit("ERROR: Refusing to run tests with ENV=prod", returncode=1)

    # Force test environment for all tests
    os.environ["ENV"] = "test"
