"""Add named colors and archival state to the shared tag catalog."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_fixed_tags"
down_revision: str | None = "0008_mcp_api_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TAG_COLORS = "'rose', 'sea-glass', 'amber', 'slate', 'plum', 'violet', 'sand', 'destructive'"


def upgrade() -> None:
    with op.batch_alter_table("tags") as batch_op:
        batch_op.add_column(
            sa.Column("color", sa.String(length=16), nullable=False, server_default="slate")
        )
        batch_op.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_check_constraint("ck_tags_color", f"color IN ({TAG_COLORS})")

    op.create_index(
        "ix_tags_user_archived_name",
        "tags",
        ["user_id", "archived_at", "name"],
    )


def downgrade() -> None:
    op.drop_index("ix_tags_user_archived_name", table_name="tags")
    with op.batch_alter_table("tags") as batch_op:
        batch_op.drop_constraint("ck_tags_color", type_="check")
        batch_op.drop_column("archived_at")
        batch_op.drop_column("color")
