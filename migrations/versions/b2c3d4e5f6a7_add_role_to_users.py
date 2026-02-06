"""add role to users

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-06 00:00:00.000000

"""

import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add role column to users table."""
    op.add_column(
        "users",
        sa.Column("role", sa.String(20), nullable=False, server_default="user"),
    )

    admin_tid = os.environ.get("ADMIN_TELEGRAM_ID")
    if admin_tid:
        conn = op.get_bind()
        conn.execute(
            sa.text(
                "INSERT INTO users (telegram_id, name, role) "
                "VALUES (:tid, 'Admin', 'admin') "
                "ON CONFLICT (telegram_id) DO UPDATE SET role = 'admin'"
            ),
            {"tid": int(admin_tid)},
        )


def downgrade() -> None:
    """Remove role column from users table."""
    op.drop_column("users", "role")
