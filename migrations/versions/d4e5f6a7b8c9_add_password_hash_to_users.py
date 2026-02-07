"""add password_hash to users

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-02-07 00:00:00.000000

"""

import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add password_hash column and set default password for existing users."""
    # Add the password_hash column
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))

    # If ADMIN_DEFAULT_PASSWORD is set, hash it and apply to all existing users
    # Import bcrypt at function level to avoid module-level import issues
    admin_default_password = os.getenv("ADMIN_DEFAULT_PASSWORD")
    if admin_default_password:
        import bcrypt

        hashed = bcrypt.hashpw(admin_default_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        # Update all existing users with the default password hash
        connection = op.get_bind()
        connection.execute(sa.text("UPDATE users SET password_hash = :hash"), {"hash": hashed})


def downgrade() -> None:
    """Remove password_hash column from users table."""
    op.drop_column("users", "password_hash")
