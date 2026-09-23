"""Normalize note bodies to sanitized HTML and rebuild the text index."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from cortex_backend.memory.content import html_to_text, normalize_note_body

revision: str = "0007_notes_html_content"
down_revision: str | None = "0006_notes_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Convert legacy Markdown bodies and rebuild FTS with visible text."""

    connection = op.get_bind()
    notes = connection.execute(sa.text("SELECT id, title, body FROM notes")).mappings().all()

    connection.execute(sa.text("DELETE FROM notes_fts"))
    for note in notes:
        body = normalize_note_body(note["body"])
        connection.execute(
            sa.text("UPDATE notes SET body = :body WHERE id = :note_id"),
            {"body": body, "note_id": note["id"]},
        )
        tags = connection.execute(
            sa.text(
                "SELECT group_concat(tags.name, ' ') "
                "FROM note_tags JOIN tags ON tags.id = note_tags.tag_id "
                "WHERE note_tags.note_id = :note_id"
            ),
            {"note_id": note["id"]},
        ).scalar_one()
        connection.execute(
            sa.text(
                "INSERT INTO notes_fts (note_id, title, body, tags) "
                "VALUES (:note_id, :title, :body, :tags)"
            ),
            {
                "note_id": note["id"],
                "title": note["title"] or "",
                "body": html_to_text(body),
                "tags": tags or "",
            },
        )


def downgrade() -> None:
    """Keep converted content intact; restore a pre-migration backup to roll back."""

    # The data conversion is intentionally forward-only and has no schema object
    # to remove. A backup is the rollback mechanism for the content format.
