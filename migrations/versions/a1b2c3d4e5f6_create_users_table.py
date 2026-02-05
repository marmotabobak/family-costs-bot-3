"""create users table

Revision ID: a1b2c3d4e5f6
Revises: 5820802edcb7
Create Date: 2026-02-05 12:00:00.000000

"""

import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "5820802edcb7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_id", name="uq_users_telegram_id"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    # Seed users from ALLOWED_USER_IDS env var (idempotent)
    allowed_ids_str = os.environ.get("ALLOWED_USER_IDS", "")
    if allowed_ids_str:
        ids_str = allowed_ids_str.strip().strip("[]")
        user_ids = [int(uid.strip()) for uid in ids_str.split(",") if uid.strip()]
        if user_ids:
            conn = op.get_bind()
            for uid in user_ids:
                conn.execute(
                    sa.text(
                        "INSERT INTO users (telegram_id, name) "
                        "VALUES (:tid, :name) "
                        "ON CONFLICT (telegram_id) DO NOTHING"
                    ),
                    {"tid": uid, "name": f"User_{uid}"},
                )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_table("users")
