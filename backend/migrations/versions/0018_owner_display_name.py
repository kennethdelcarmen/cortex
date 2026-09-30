"""Add an optional owner display name."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_owner_display_name"
down_revision: str | None = "0017_money_transaction_names"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.String(length=80), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "display_name")
