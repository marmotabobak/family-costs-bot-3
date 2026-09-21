"""add currency support

Adds ``currencies`` and ``exchange_rates`` tables, extends ``messages`` with
``amount`` and ``currency_id`` columns, inserts RUB as the base currency, and
backfills ``amount``/``currency_id`` for existing messages whose ``text``
matches the legacy ``<name> <number>`` format.

Revision ID: e1f2a3b4c5d6
Revises: d4e5f6a7b8c9
Create Date: 2026-09-21 00:00:00.000000
"""

from decimal import Decimal, InvalidOperation
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Inline amount parser — frozen copy of the legacy rsplit logic.
# Must NOT import from bot.* to keep migrations self-contained.
# ---------------------------------------------------------------------------

def _parse_amount(text: str | None) -> Decimal | None:
    """Parse the amount from a legacy ``messages.text`` value.

    The legacy format is ``"<name> <amount>"`` where the amount is the last
    whitespace-separated token and may use a comma as the decimal separator.

    Returns ``None`` for empty / unparseable input so callers can leave those
    rows as ``NULL``.

    Examples::

        >>> _parse_amount("coffee 250")
        Decimal('250')
        >>> _parse_amount("a b c 12,50")
        Decimal('12.50')
        >>> _parse_amount("malformed")
        None
        >>> _parse_amount("")
        None
    """
    if not text:
        return None
    parts = text.rsplit(maxsplit=1)
    if len(parts) != 2:
        return None
    try:
        return Decimal(parts[1].replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    """Apply currency support schema changes."""

    # 1. Create ``currencies`` table
    op.create_table(
        "currencies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(3), nullable=False),
        sa.Column("is_base", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("default_rate", sa.Numeric(20, 10), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        sa.CheckConstraint("default_rate > 0", name="currencies_default_rate_positive"),
        sa.CheckConstraint("code ~ '^[A-Z]{3}$'", name="currencies_code_format"),
    )

    # 2. Create ``exchange_rates`` table
    op.create_table(
        "exchange_rates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("currency_id", sa.Integer(), nullable=False),
        sa.Column("rate", sa.Numeric(20, 10), nullable=False),
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["currency_id"],
            ["currencies.id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("rate > 0", name="exchange_rates_rate_positive"),
        sa.UniqueConstraint(
            "currency_id",
            "rate_date",
            name="uq_exchange_rates_currency_date",
        ),
    )
    op.create_index("idx_exchange_rates_currency_id", "exchange_rates", ["currency_id"])

    # 3. Partial unique index: at most one ``is_base=TRUE`` currency
    op.create_index(
        "idx_currencies_single_base",
        "currencies",
        ["is_base"],
        unique=True,
        postgresql_where=sa.text("is_base = TRUE"),
    )

    # 4. Seed RUB as the base currency
    op.execute(
        "INSERT INTO currencies (code, is_base, default_rate) VALUES ('RUB', TRUE, 1)"
    )

    # 5. Add new columns to ``messages``
    op.add_column("messages", sa.Column("amount", sa.Numeric(20, 4), nullable=True))
    op.add_column(
        "messages",
        sa.Column("currency_id", sa.Integer(), nullable=True),
    )
    op.create_index("idx_messages_currency_id", "messages", ["currency_id"])
    op.create_foreign_key(
        "fk_messages_currency_id",
        "messages",
        "currencies",
        ["currency_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # 6. Backfill ``amount`` and ``currency_id`` from ``messages.text``
    conn = op.get_bind()
    rub_id = conn.execute(
        sa.text("SELECT id FROM currencies WHERE code = 'RUB'")
    ).scalar()

    rows = conn.execute(sa.text("SELECT id, text FROM messages")).fetchall()
    for row_id, text in rows:
        amount = _parse_amount(text)
        if amount is not None:
            conn.execute(
                sa.text(
                    "UPDATE messages SET amount = :a, currency_id = :c WHERE id = :i"
                ),
                {"a": str(amount), "c": rub_id, "i": row_id},
            )


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    """Remove currency support schema changes."""

    # Drop FK and columns from messages first
    op.drop_constraint("fk_messages_currency_id", "messages", type_="foreignkey")
    op.drop_index("idx_messages_currency_id", table_name="messages")
    op.drop_column("messages", "currency_id")
    op.drop_column("messages", "amount")

    # Drop exchange_rates (FK to currencies, safe to drop first)
    op.drop_index("idx_exchange_rates_currency_id", table_name="exchange_rates")
    op.drop_table("exchange_rates")

    # Drop currencies (partial unique index is dropped with the table)
    op.drop_table("currencies")
