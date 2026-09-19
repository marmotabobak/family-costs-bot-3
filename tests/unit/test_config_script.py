"""Tests for scripts/config.py."""

import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Load scripts/config.py without executing main()
_spec = importlib.util.spec_from_file_location(
    "config_script",
    Path(__file__).resolve().parent.parent.parent / "scripts" / "config.py",
)
assert _spec is not None
config_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(config_mod)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# load_env
# ---------------------------------------------------------------------------


class TestLoadEnv:
    def test_parses_key_value_pairs(self, tmp_path):
        (tmp_path / ".env").write_text("FOO=bar\nBAZ=qux\n")
        assert config_mod.load_env(tmp_path / ".env") == {"FOO": "bar", "BAZ": "qux"}

    def test_ignores_comment_lines(self, tmp_path):
        (tmp_path / ".env").write_text("# comment\nFOO=bar\n")
        assert config_mod.load_env(tmp_path / ".env") == {"FOO": "bar"}

    def test_ignores_empty_lines(self, tmp_path):
        (tmp_path / ".env").write_text("\nFOO=bar\n\nBAZ=qux\n")
        assert config_mod.load_env(tmp_path / ".env") == {"FOO": "bar", "BAZ": "qux"}

    def test_value_containing_equals(self, tmp_path):
        (tmp_path / ".env").write_text(
            "DATABASE_URL=postgresql+asyncpg://u:p@localhost/db\n"
        )
        result = config_mod.load_env(tmp_path / ".env")
        assert result["DATABASE_URL"] == "postgresql+asyncpg://u:p@localhost/db"

    def test_empty_value(self, tmp_path):
        (tmp_path / ".env").write_text("FOO=\n")
        assert config_mod.load_env(tmp_path / ".env") == {"FOO": ""}

    def test_strips_whitespace_from_key(self, tmp_path):
        (tmp_path / ".env").write_text("  FOO  =bar\n")
        assert config_mod.load_env(tmp_path / ".env") == {"FOO": "bar"}


# ---------------------------------------------------------------------------
# update_env_file
# ---------------------------------------------------------------------------


class TestUpdateEnvFile:
    def test_replaces_existing_key(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("FOO=old\n")
        config_mod.update_env_file(f, {"FOO": "new"})
        assert config_mod.load_env(f)["FOO"] == "new"

    def test_appends_missing_key(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("FOO=bar\n")
        config_mod.update_env_file(f, {"BAZ": "qux"})
        result = config_mod.load_env(f)
        assert result["FOO"] == "bar"
        assert result["BAZ"] == "qux"

    def test_preserves_comments_and_blank_lines(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("# comment\n\nFOO=bar\n")
        config_mod.update_env_file(f, {"FOO": "new"})
        content = f.read_text()
        assert "# comment" in content
        assert "FOO=new" in content

    def test_replaces_multiple_keys(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("A=1\nB=2\n")
        config_mod.update_env_file(f, {"A": "10", "B": "20"})
        assert config_mod.load_env(f) == {"A": "10", "B": "20"}

    def test_creates_file_when_not_exists(self, tmp_path):
        f = tmp_path / ".env"
        config_mod.update_env_file(f, {"FOO": "bar"})
        assert f.exists()
        assert "FOO=bar" in f.read_text()

    def test_does_not_duplicate_existing_key(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("FOO=old\n")
        config_mod.update_env_file(f, {"FOO": "new"})
        lines = [line for line in f.read_text().splitlines() if line.startswith("FOO=")]
        assert len(lines) == 1


# ---------------------------------------------------------------------------
# build_database_url
# ---------------------------------------------------------------------------


class TestBuildDatabaseUrl:
    def test_builds_correct_url(self):
        env = {
            "POSTGRES_USER": "myuser",
            "POSTGRES_PASSWORD": "mypass",
            "POSTGRES_DB": "mydb",
            "POSTGRES_PORT": "5433",
        }
        url = config_mod.build_database_url(env)
        assert url == "postgresql+asyncpg://myuser:mypass@localhost:5433/mydb"

    def test_uses_defaults_for_missing_keys(self):
        url = config_mod.build_database_url({})
        assert url.startswith("postgresql+asyncpg://postgres:")
        assert "@localhost:5432/" in url
        assert url.endswith("family-costs-bot")

    def test_password_with_special_chars(self):
        env = {
            "POSTGRES_USER": "u",
            "POSTGRES_PASSWORD": "p@ss!word",
            "POSTGRES_DB": "db",
            "POSTGRES_PORT": "5432",
        }
        url = config_mod.build_database_url(env)
        assert "p@ss!word@localhost" in url


# ---------------------------------------------------------------------------
# _validate_env
# ---------------------------------------------------------------------------


def _complete_env_text() -> str:
    return (
        "BOT_TOKEN=123456:ABC-DEF\n"
        "POSTGRES_USER=postgres\n"
        "POSTGRES_PASSWORD=pass\n"
        "POSTGRES_DB=mydb\n"
        "POSTGRES_PORT=5432\n"
        "DATABASE_URL=postgresql+asyncpg://postgres:pass@localhost:5432/mydb\n"
        "ENV=prod\n"
        "ADMIN_TELEGRAM_ID=12345\n"
        "ADMIN_DEFAULT_PASSWORD=secret\n"
        "WEB_BASE_URL=http://localhost\n"
        "WEB_PORT=8000\n"
        "WEB_ROOT_PATH=/family-costs-bot\n"
    )


class TestValidateEnv:
    def test_does_nothing_when_complete(self, tmp_path, capsys):
        f = tmp_path / ".env"
        f.write_text(_complete_env_text())
        config_mod._validate_env(f)
        assert ".env is complete" in capsys.readouterr().out

    def test_reports_missing_keys(self, tmp_path, capsys):
        f = tmp_path / ".env"
        f.write_text("BOT_TOKEN=123456:ABC\n")
        with patch("builtins.input", return_value="value"), \
             patch("getpass.getpass", return_value="secret"):
            config_mod._validate_env(f)
        assert "Missing" in capsys.readouterr().out

    def test_updates_file_with_collected_value(self, tmp_path):
        f = tmp_path / ".env"
        # Everything present except ADMIN_DEFAULT_PASSWORD
        f.write_text(
            "BOT_TOKEN=123456:ABC\n"
            "POSTGRES_USER=postgres\n"
            "POSTGRES_PASSWORD=pass\n"
            "POSTGRES_DB=mydb\n"
            "POSTGRES_PORT=5432\n"
            "DATABASE_URL=postgresql+asyncpg://postgres:pass@localhost:5432/mydb\n"
            "ENV=prod\n"
            "ADMIN_TELEGRAM_ID=12345\n"
            "WEB_BASE_URL=http://localhost\n"
            "WEB_PORT=8000\n"
            "WEB_ROOT_PATH=/family-costs-bot\n"
        )
        with patch("builtins.input", return_value="value"), \
             patch("getpass.getpass", return_value="newpass"):
            config_mod._validate_env(f)
        assert config_mod.load_env(f)["ADMIN_DEFAULT_PASSWORD"] == "newpass"

    def test_rebuilds_database_url_when_pg_key_missing(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text(
            "BOT_TOKEN=123456:ABC\n"
            # POSTGRES_USER and DATABASE_URL both absent
            "POSTGRES_PASSWORD=pass\n"
            "POSTGRES_DB=mydb\n"
            "POSTGRES_PORT=5432\n"
            "ENV=prod\n"
            "ADMIN_TELEGRAM_ID=12345\n"
            "ADMIN_DEFAULT_PASSWORD=secret\n"
            "WEB_BASE_URL=http://localhost\n"
            "WEB_PORT=8000\n"
            "WEB_ROOT_PATH=/family-costs-bot\n"
        )
        with patch("builtins.input", return_value="newuser"), \
             patch("getpass.getpass", return_value="secret"):
            config_mod._validate_env(f)
        result = config_mod.load_env(f)
        assert "newuser" in result.get("DATABASE_URL", "")

    def test_prints_updated_when_keys_added(self, tmp_path, capsys):
        f = tmp_path / ".env"
        f.write_text("BOT_TOKEN=123456:ABC\n")
        with patch("builtins.input", return_value="value"), \
             patch("getpass.getpass", return_value="secret"):
            config_mod._validate_env(f)
        assert ".env updated" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# _create_env
# ---------------------------------------------------------------------------


def _patch_create_inputs(
    *,
    token="123456:VALID-TOKEN-HERE",
    pg_user="postgres",
    pg_password="pgpass",
    pg_db="family-costs-bot",
    pg_port="5432",
    env="prod",
    admin_tid="99999",
    admin_name="Admin",
    admin_pass="adminpass",
    web_base_url="http://localhost",
    web_port="8000",
    web_root="/family-costs-bot",
):
    """Return a pair of patch context managers (getpass, input) for _create_env."""
    secrets = iter([token, pg_password, admin_pass])
    plain = iter([pg_user, pg_db, pg_port, env, admin_tid, admin_name, web_base_url, web_port, web_root])
    return (
        patch("getpass.getpass", side_effect=secrets),
        patch("builtins.input", side_effect=plain),
    )


class TestCreateEnv:
    def test_creates_file_with_all_values(self, tmp_path):
        env_file = tmp_path / ".env"
        gp, inp = _patch_create_inputs()
        with gp, inp:
            config_mod._create_env(env_file)
        assert env_file.exists()
        result = config_mod.load_env(env_file)
        assert result["BOT_TOKEN"] == "123456:VALID-TOKEN-HERE"
        assert result["POSTGRES_USER"] == "postgres"
        assert result["ADMIN_TELEGRAM_ID"] == "99999"
        assert result["ENV"] == "prod"
        assert "postgresql+asyncpg://" in result["DATABASE_URL"]

    def test_database_url_built_from_pg_values(self, tmp_path):
        env_file = tmp_path / ".env"
        gp, inp = _patch_create_inputs(pg_user="myuser", pg_password="mypass", pg_db="mydb", pg_port="5433")
        with gp, inp:
            config_mod._create_env(env_file)
        result = config_mod.load_env(env_file)
        assert result["DATABASE_URL"] == "postgresql+asyncpg://myuser:mypass@localhost:5433/mydb"

    def test_retries_on_invalid_bot_token(self, tmp_path):
        env_file = tmp_path / ".env"
        # Token must be ≥ 20 chars and contain ":"
        good_token = "1234567890:ABCDEFGHIJK"
        secrets = iter(["badtoken", good_token, "pgpass", "adminpass"])
        plain = iter(["postgres", "mydb", "5432", "prod", "12345", "Admin", "http://localhost", "8000", "/bot"])
        with patch("getpass.getpass", side_effect=secrets), \
             patch("builtins.input", side_effect=plain):
            config_mod._create_env(env_file)
        assert config_mod.load_env(env_file)["BOT_TOKEN"] == good_token

    def test_retries_on_non_numeric_admin_id(self, tmp_path):
        env_file = tmp_path / ".env"
        secrets = iter(["1234567890:ABCDEFGHIJK", "pgpass", "adminpass"])
        plain = iter(["postgres", "mydb", "5432", "prod", "not-a-number", "99999", "Admin", "http://localhost", "8000", "/bot"])
        with patch("getpass.getpass", side_effect=secrets), \
             patch("builtins.input", side_effect=plain):
            config_mod._create_env(env_file)
        assert config_mod.load_env(env_file)["ADMIN_TELEGRAM_ID"] == "99999"

    def test_prints_next_steps(self, tmp_path, capsys):
        env_file = tmp_path / ".env"
        gp, inp = _patch_create_inputs()
        with gp, inp:
            config_mod._create_env(env_file)
        out = capsys.readouterr().out
        assert "make up" in out
        assert "make admin" in out


# ---------------------------------------------------------------------------
# cmd_env
# ---------------------------------------------------------------------------


class TestCmdEnv:
    def test_calls_create_env_when_no_file(self, tmp_path):
        with patch.object(config_mod, "ROOT", tmp_path), \
             patch.object(config_mod, "_create_env") as mock_create:
            config_mod.cmd_env()
        mock_create.assert_called_once_with(tmp_path / ".env")

    def test_calls_validate_env_when_file_exists(self, tmp_path):
        (tmp_path / ".env").write_text("FOO=bar\n")
        with patch.object(config_mod, "ROOT", tmp_path), \
             patch.object(config_mod, "_validate_env") as mock_validate:
            config_mod.cmd_env()
        mock_validate.assert_called_once_with(tmp_path / ".env")


# ---------------------------------------------------------------------------
# cmd_admin
# ---------------------------------------------------------------------------


def _write_admin_env(tmp_path, **overrides):
    vals = {
        "DATABASE_URL": "postgresql+asyncpg://u:p@localhost:5432/db",
        "ADMIN_TELEGRAM_ID": "12345",
        "ADMIN_DEFAULT_PASSWORD": "secret",
    }
    vals.update(overrides)
    (tmp_path / ".env").write_text("\n".join(f"{k}={v}" for k, v in vals.items()) + "\n")


class TestCmdAdmin:
    def test_exits_when_no_env_file(self, tmp_path):
        with patch.object(config_mod, "ROOT", tmp_path):
            with pytest.raises(SystemExit):
                config_mod.cmd_admin()

    def test_exits_when_database_url_missing(self, tmp_path):
        (tmp_path / ".env").write_text("ADMIN_TELEGRAM_ID=12345\n")
        with patch.object(config_mod, "ROOT", tmp_path):
            with pytest.raises(SystemExit):
                config_mod.cmd_admin()

    def test_exits_when_admin_telegram_id_missing(self, tmp_path):
        (tmp_path / ".env").write_text(
            "DATABASE_URL=postgresql+asyncpg://u:p@localhost/db\n"
        )
        with patch.object(config_mod, "ROOT", tmp_path):
            with pytest.raises(SystemExit):
                config_mod.cmd_admin()

    def test_exits_when_admin_telegram_id_not_numeric(self, tmp_path):
        (tmp_path / ".env").write_text(
            "DATABASE_URL=postgresql+asyncpg://u:p@localhost/db\n"
            "ADMIN_TELEGRAM_ID=not-a-number\n"
        )
        with patch.object(config_mod, "ROOT", tmp_path):
            with pytest.raises(SystemExit):
                config_mod.cmd_admin()

    def test_reports_existing_admin(self, tmp_path, capsys):
        _write_admin_env(tmp_path)
        with patch.object(config_mod, "ROOT", tmp_path), \
             patch.object(config_mod, "_find_admin", AsyncMock(return_value=True)):
            config_mod.cmd_admin()
        assert "Admin user exists" in capsys.readouterr().out

    def test_reports_admin_not_found(self, tmp_path, capsys):
        _write_admin_env(tmp_path)
        with patch.object(config_mod, "ROOT", tmp_path), \
             patch.object(config_mod, "_find_admin", AsyncMock(return_value=False)), \
             patch("builtins.input", return_value="n"):
            config_mod.cmd_admin()
        assert "not found" in capsys.readouterr().out

    def test_skips_creation_when_declined(self, tmp_path):
        _write_admin_env(tmp_path)
        mock_insert = AsyncMock()
        with patch.object(config_mod, "ROOT", tmp_path), \
             patch.object(config_mod, "_find_admin", AsyncMock(return_value=False)), \
             patch.object(config_mod, "_insert_admin", mock_insert), \
             patch("builtins.input", return_value="n"):
            config_mod.cmd_admin()
        mock_insert.assert_not_called()

    def test_creates_admin_when_confirmed(self, tmp_path):
        _write_admin_env(tmp_path)
        mock_insert = AsyncMock()
        with patch.object(config_mod, "ROOT", tmp_path), \
             patch.object(config_mod, "_find_admin", AsyncMock(return_value=False)), \
             patch.object(config_mod, "_insert_admin", mock_insert), \
             patch("builtins.input", side_effect=["y", "Admin"]), \
             patch("getpass.getpass", return_value="newpass"), \
             patch("bcrypt.hashpw", return_value=b"$2b$12$hashed"):
            config_mod.cmd_admin()
        mock_insert.assert_called_once()

    def test_uses_default_password_from_env(self, tmp_path):
        _write_admin_env(tmp_path, ADMIN_DEFAULT_PASSWORD="envpass")
        mock_insert = AsyncMock()
        with patch.object(config_mod, "ROOT", tmp_path), \
             patch.object(config_mod, "_find_admin", AsyncMock(return_value=False)), \
             patch.object(config_mod, "_insert_admin", mock_insert), \
             patch("builtins.input", side_effect=["y", "Admin"]), \
             patch("getpass.getpass", return_value=""), \
             patch("bcrypt.hashpw", return_value=b"$2b$12$hashed") as mock_hash:
            config_mod.cmd_admin()
        mock_hash.assert_called_once_with(b"envpass", mock_hash.call_args[0][1])

    def test_exits_on_db_connection_error(self, tmp_path, capsys):
        _write_admin_env(tmp_path)
        with patch.object(config_mod, "ROOT", tmp_path), \
             patch.object(config_mod, "_find_admin", AsyncMock(side_effect=Exception("connection refused"))):
            with pytest.raises(SystemExit):
                config_mod.cmd_admin()
        out = capsys.readouterr().out
        assert "connect" in out.lower() or "database" in out.lower()

    def test_exits_on_insert_failure(self, tmp_path, capsys):
        _write_admin_env(tmp_path)
        with patch.object(config_mod, "ROOT", tmp_path), \
             patch.object(config_mod, "_find_admin", AsyncMock(return_value=False)), \
             patch.object(config_mod, "_insert_admin", AsyncMock(side_effect=Exception("insert failed"))), \
             patch("builtins.input", side_effect=["y", "Admin"]), \
             patch("getpass.getpass", return_value="pass"), \
             patch("bcrypt.hashpw", return_value=b"$2b$12$hashed"):
            with pytest.raises(SystemExit):
                config_mod.cmd_admin()
