"""add_check_constraint_on_user_id

Revision ID: 5820802edcb7
Revises: 4c5c3f6f8088
Create Date: 2026-01-05 00:56:33.309374

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '5820802edcb7'
down_revision: Union[str, Sequence[str], None] = '4c5c3f6f8088'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_check_constraint(
        "messages_user_id_positive",
        "messages",
        "user_id > 0",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "messages_user_id_positive",
        "messages",
        type_="check",
    )
