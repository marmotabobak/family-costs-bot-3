"""messages user_id to bigint

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-02-06 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Widen messages.user_id from Integer to BigInteger for large Telegram IDs."""
    op.alter_column(
        "messages",
        "user_id",
        type_=sa.BigInteger(),
        existing_type=sa.Integer(),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Revert messages.user_id back to Integer."""
    op.alter_column(
        "messages",
        "user_id",
        type_=sa.Integer(),
        existing_type=sa.BigInteger(),
        existing_nullable=False,
    )
