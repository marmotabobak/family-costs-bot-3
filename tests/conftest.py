"""Root conftest - safety checks and test environment setup."""

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
