"""Context assembly behavior for future RAG answer generation."""

import pytest

from cortex_backend.chunking.context import assemble_context
from cortex_backend.chunking.service import ChunkSearchRecord, ChunkSourceType


def _chunk(
    chunk_id: str,
    text: str,
    *,
    source_type: ChunkSourceType = "note",
    source_id: str = "source-1",
    source_title: str | None = "Example source",
    rank: int = 1,
    file_ids: list[str] | None = None,
    file_names: list[str] | None = None,
) -> ChunkSearchRecord:
    return ChunkSearchRecord(
        id=chunk_id,
        user_id="user-1",
        source_type=source_type,
        source_id=source_id,
        source_version="version-1",
        source_title=source_title,
        ordinal=rank - 1,
        text=text,
        rank=rank,
        score=1.0 / rank,
        file_ids=file_ids or [],
        file_names=file_names or [],
    )


def test_assembly_preserves_rank_order_and_budget() -> None:
    first = _chunk("chunk-1", "First ranked passage.", rank=1)
    second = _chunk("chunk-2", "Second ranked passage with more detail.", rank=2)
    third = _chunk("chunk-3", "Third ranked passage with more detail.", rank=3)
    first_only = assemble_context("What matters?", [first])

    package = assemble_context(
        "What matters?",
        [first, second, third],
        max_characters=first_only.character_count + 1,
    )

    assert [passage.chunk_id for passage in package.passages] == ["chunk-1"]
    assert package.character_count <= package.max_characters
    assert package.context_text.startswith("[1] Example source\nFirst ranked passage.")


def test_assembly_removes_exact_duplicates_but_keeps_distinct_text() -> None:
    package = assemble_context(
        "Which notes help?",
        [
            _chunk("chunk-1", "Same text appears here."),
            _chunk("chunk-2", "  same   text appears here. ", rank=2),
            _chunk("chunk-3", "This passage adds a different detail.", rank=3),
        ],
    )

    assert [passage.chunk_id for passage in package.passages] == ["chunk-1", "chunk-3"]


def test_assembly_removes_high_overlap_and_keeps_meaningful_difference() -> None:
    package = assemble_context(
        "Which details matter?",
        [
            _chunk("chunk-1", "alpha beta gamma delta"),
            _chunk("chunk-2", "ALPHA beta gamma delta epsilon", rank=2),
            _chunk("chunk-3", "alpha beta gamma new information", rank=3),
        ],
    )

    assert [passage.chunk_id for passage in package.passages] == ["chunk-1", "chunk-3"]


def test_assembly_keeps_normal_neighboring_chunks_with_limited_overlap() -> None:
    package = assemble_context(
        "What happened?",
        [
            _chunk("chunk-1", "one two three four five six seven eight nine ten"),
            _chunk("chunk-2", "nine ten eleven twelve thirteen fourteen fifteen sixteen"),
        ],
    )

    assert [passage.chunk_id for passage in package.passages] == ["chunk-1", "chunk-2"]


def test_assembly_attaches_citations_and_source_metadata() -> None:
    package = assemble_context(
        "Where are the sources?",
        [
            _chunk("note-chunk", "Note evidence.", source_type="note", source_id="note-1"),
            _chunk(
                "task-chunk",
                "Task evidence.",
                source_type="task",
                source_id="task-1",
                source_title="Important task",
                rank=2,
            ),
            _chunk(
                "file-chunk",
                "File evidence.",
                source_type="file",
                source_id="hash-1",
                source_title=None,
                rank=3,
                file_ids=["file-1", "file-2"],
                file_names=["receipt.pdf", "receipt-copy.pdf"],
            ),
        ],
    )

    assert [passage.citation for passage in package.passages] == ["[1]", "[2]", "[3]"]
    assert package.passages[0].source_name == "Example source"
    assert package.passages[1].source_name == "Important task"
    assert package.passages[2].source_name == "receipt.pdf, receipt-copy.pdf"
    assert package.passages[2].source_id == "hash-1"
    assert package.passages[2].file_ids == ("file-1", "file-2")
    assert package.passages[2].file_names == ("receipt.pdf", "receipt-copy.pdf")
    assert package.has_context is True
    assert package.empty_reason is None


def test_empty_search_results_return_a_safe_empty_package() -> None:
    package = assemble_context("What should I do?", [])

    assert package.has_context is False
    assert package.context_text == ""
    assert package.passages == ()
    assert package.character_count == 0
    assert package.empty_reason == "no_results"


def test_blank_passages_and_too_small_budget_return_reasons() -> None:
    blank = assemble_context("Is there anything?", [_chunk("blank", "!!!")])
    too_small = assemble_context(
        "Is there anything?",
        [_chunk("text", "Useful evidence.")],
        max_characters=1,
    )

    assert blank.has_context is False
    assert blank.empty_reason == "no_usable_text"
    assert too_small.has_context is False
    assert too_small.empty_reason == "budget_too_small"


def test_assembly_rejects_invalid_question_and_budget() -> None:
    with pytest.raises(ValueError, match="question must contain content"):
        assemble_context("  \n\t", [])
    with pytest.raises(ValueError, match="max_characters must be positive"):
        assemble_context("A valid question", [], max_characters=0)


def test_assembly_is_deterministic() -> None:
    chunks = [
        _chunk("chunk-1", "First passage."),
        _chunk("chunk-2", "Second passage.", rank=2),
    ]

    assert assemble_context("What is known?", chunks) == assemble_context("What is known?", chunks)
