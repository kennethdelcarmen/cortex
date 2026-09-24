"""Normalize legacy file-context timestamps for SQLite comparisons."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_normalize_file_context_timestamps"
down_revision: str | None = "0011_file_context_pipeline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Convert ISO timestamps with ``T`` and offsets to SQLite datetime text."""

    connection = op.get_bind()
    connection.execute(
        sa.text(
            "UPDATE file_context_jobs "
            "SET available_at = datetime(available_at), "
            "created_at = datetime(created_at), "
            "updated_at = datetime(updated_at), "
            "lease_expires_at = CASE "
            "WHEN lease_expires_at IS NULL THEN NULL "
            "ELSE datetime(lease_expires_at) END "
            "WHERE available_at LIKE '%T%' "
            "OR created_at LIKE '%T%' "
            "OR updated_at LIKE '%T%' "
            "OR lease_expires_at LIKE '%T%'"
        )
    )


def downgrade() -> None:
    """Leave normalized values in place; the conversion is intentionally one-way."""
