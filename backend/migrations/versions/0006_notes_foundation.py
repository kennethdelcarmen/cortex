"""Create the owner-scoped notes schema and local full-text index."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_notes_foundation"
down_revision: str | None = "0005_task_recurrencies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("journal_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notes_owner_deleted_updated",
        "notes",
        ["user_id", "deleted_at", "updated_at", "id"],
    )
    op.create_index(
        "ix_notes_owner_deleted_journal",
        "notes",
        ["user_id", "deleted_at", "journal_date", "updated_at", "id"],
    )
    op.create_table(
        "note_tags",
        sa.Column("note_id", sa.String(length=36), nullable=False),
        sa.Column("tag_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("note_id", "tag_id"),
    )
    op.create_index("ix_note_tags_tag_id", "note_tags", ["tag_id"])
    op.execute(
        sa.text(
            "CREATE VIRTUAL TABLE notes_fts USING fts5("
            "note_id UNINDEXED, title, body, tags, tokenize='unicode61'"
            ")"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE notes_fts"))
    op.drop_index("ix_note_tags_tag_id", table_name="note_tags")
    op.drop_table("note_tags")
    op.drop_index("ix_notes_owner_deleted_journal", table_name="notes")
    op.drop_index("ix_notes_owner_deleted_updated", table_name="notes")
    op.drop_table("notes")
