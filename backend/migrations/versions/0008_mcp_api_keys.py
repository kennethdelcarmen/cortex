"""Add owner-scoped MCP bearer credentials."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_mcp_api_keys"
down_revision: str | None = "0007_notes_html_content"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mcp_api_keys",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_mcp_api_keys_user_id", "mcp_api_keys", ["user_id"], unique=True)
    op.create_index("uq_mcp_api_keys_key_hash", "mcp_api_keys", ["key_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_mcp_api_keys_key_hash", table_name="mcp_api_keys")
    op.drop_index("uq_mcp_api_keys_user_id", table_name="mcp_api_keys")
    op.drop_table("mcp_api_keys")
