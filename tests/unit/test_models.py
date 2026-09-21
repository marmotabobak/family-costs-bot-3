"""Unit tests for SQLAlchemy models.

These tests verify table names, column definitions, and constraint names without
requiring a live database connection — they inspect model metadata only.
"""


from bot.db.models import Currency, ExchangeRate, Message, User


class TestCurrencyModel:
    """Task 1.1 — Currency model structure."""

    def test_tablename(self):
        assert Currency.__tablename__ == "currencies"

    def test_id_column(self):
        col = Currency.__table__.c["id"]
        assert col.primary_key

    def test_code_column(self):
        col = Currency.__table__.c["code"]
        assert not col.nullable
        assert col.unique

    def test_is_base_column(self):
        col = Currency.__table__.c["is_base"]
        assert not col.nullable

    def test_default_rate_column(self):
        col = Currency.__table__.c["default_rate"]
        assert not col.nullable

    def test_created_at_column(self):
        assert "created_at" in Currency.__table__.c

    def test_check_constraint_default_rate_positive(self):
        constraint_names = {c.name for c in Currency.__table__.constraints}
        assert "currencies_default_rate_positive" in constraint_names

    def test_check_constraint_code_format(self):
        constraint_names = {c.name for c in Currency.__table__.constraints}
        assert "currencies_code_format" in constraint_names


class TestExchangeRateModel:
    """Task 1.1 — ExchangeRate model structure."""

    def test_tablename(self):
        assert ExchangeRate.__tablename__ == "exchange_rates"

    def test_id_column(self):
        col = ExchangeRate.__table__.c["id"]
        assert col.primary_key

    def test_currency_id_column(self):
        col = ExchangeRate.__table__.c["currency_id"]
        assert not col.nullable
        # Verify the foreign key target
        fk = next(iter(col.foreign_keys))
        assert fk.target_fullname == "currencies.id"

    def test_rate_column(self):
        col = ExchangeRate.__table__.c["rate"]
        assert not col.nullable

    def test_rate_date_column(self):
        col = ExchangeRate.__table__.c["rate_date"]
        assert not col.nullable

    def test_check_constraint_rate_positive(self):
        constraint_names = {c.name for c in ExchangeRate.__table__.constraints}
        assert "exchange_rates_rate_positive" in constraint_names

    def test_unique_constraint_currency_date(self):
        constraint_names = {c.name for c in ExchangeRate.__table__.constraints}
        assert "uq_exchange_rates_currency_date" in constraint_names


class TestMessageModelCurrencyColumns:
    """Task 1.2 — Message model currency extension."""

    def test_amount_column_exists(self):
        assert "amount" in Message.__table__.c

    def test_amount_column_nullable(self):
        col = Message.__table__.c["amount"]
        assert col.nullable

    def test_currency_id_column_exists(self):
        assert "currency_id" in Message.__table__.c

    def test_currency_id_column_nullable(self):
        col = Message.__table__.c["currency_id"]
        assert col.nullable

    def test_currency_id_foreign_key(self):
        col = Message.__table__.c["currency_id"]
        assert col.foreign_keys, "currency_id should have a FK to currencies.id"
        fk = next(iter(col.foreign_keys))
        assert fk.target_fullname == "currencies.id"

    def test_currency_id_fk_ondelete_restrict(self):
        col = Message.__table__.c["currency_id"]
        fk = next(iter(col.foreign_keys))
        assert fk.ondelete == "RESTRICT"

    def test_currency_id_indexed(self):
        col = Message.__table__.c["currency_id"]
        # Column-level index=True creates an index
        assert col.index

    def test_existing_columns_intact(self):
        """Ensure existing columns were not removed."""
        for name in ("id", "user_id", "text", "created_at"):
            assert name in Message.__table__.c


class TestUserModel:
    """Sanity check that User model is unchanged."""

    def test_tablename(self):
        assert User.__tablename__ == "users"

    def test_role_column_default(self):
        col = User.__table__.c["role"]
        assert col.server_default is not None
