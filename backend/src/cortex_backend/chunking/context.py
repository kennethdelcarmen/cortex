"""Deterministic assembly of ranked chunks into model-ready context."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from .service import ChunkSearchRecord, ChunkSourceType
from .text import normalize_source_text

DEFAULT_CONTEXT_MAX_CHARACTERS = 6_000
HIGH_OVERLAP_THRESHOLD = 0.85

EmptyContextReason = Literal["no_results", "no_usable_text", "budget_too_small"]


@dataclass(frozen=True)
class ContextPassage:
    """One selected passage and the metadata needed to cite its source."""

    citation: str
    text: str
    chunk_id: str
    source_type: ChunkSourceType
    source_id: str
    source_name: str
    source_version: str
    chunk_ordinal: int
    retrieval_rank: int
    retrieval_score: float
    file_ids: tuple[str, ...]
    file_names: tuple[str, ...]


@dataclass(frozen=True)
class ContextPackage:
    """The bounded context package passed to a future answer generator."""

    question: str
    context_text: str
    passages: tuple[ContextPassage, ...]
    character_count: int
    max_characters: int
    has_context: bool
    empty_reason: EmptyContextReason | None


def _comparison_text(value: str) -> str:
    """Normalize text for duplicate and overlap comparisons only."""

    return " ".join(value.casefold().split())


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"\w+", value, flags=re.UNICODE))


def _shorter_text_containment(left: tuple[str, ...], right: tuple[str, ...]) -> float:
    """Return the fraction of the shorter word sequence covered by the longer."""

    if not left or not right:
        return 0.0
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    overlap = sum((Counter(shorter) & Counter(longer)).values())
    return overlap / len(shorter)


def _source_name(chunk: ChunkSearchRecord) -> str:
    if chunk.source_type in {"note", "task"} and chunk.source_title:
        title = chunk.source_title.strip()
        if title:
            return title

    file_names = tuple(name.strip() for name in chunk.file_names if name.strip())
    if chunk.source_type == "file" and file_names:
        return ", ".join(file_names)

    return chunk.source_id


def _render_passage(citation: str, source_name: str, text: str) -> str:
    return f"{citation} {source_name}\n{text}"


def _package(
    *,
    question: str,
    blocks: list[str],
    passages: list[ContextPassage],
    max_characters: int,
    empty_reason: EmptyContextReason | None,
) -> ContextPackage:
    context_text = "\n\n".join(blocks)
    return ContextPackage(
        question=question,
        context_text=context_text,
        passages=tuple(passages),
        character_count=len(context_text),
        max_characters=max_characters,
        has_context=bool(passages),
        empty_reason=empty_reason,
    )


def assemble_context(
    question: str,
    chunks: Sequence[ChunkSearchRecord],
    *,
    max_characters: int = DEFAULT_CONTEXT_MAX_CHARACTERS,
) -> ContextPackage:
    """Select ranked chunks and assemble a bounded, citation-ready context.

    Chunks are expected to already be ordered from best to worst by retrieval.
    The question is included in the returned package but does not change the
    ranking or selection of the supplied chunks.
    """

    cleaned_question = " ".join(question.strip().split())
    if not cleaned_question:
        raise ValueError("question must contain content")
    if max_characters <= 0:
        raise ValueError("max_characters must be positive")

    blocks: list[str] = []
    passages: list[ContextPassage] = []
    selected_comparisons: list[tuple[str, tuple[str, ...]]] = []
    saw_usable_text = False

    for chunk in chunks:
        text = normalize_source_text(chunk.text)
        comparison = _comparison_text(text)
        word_tokens = _tokens(comparison)
        if not comparison or not word_tokens:
            continue
        saw_usable_text = True

        if any(
            comparison == selected_text
            or _shorter_text_containment(word_tokens, selected_tokens) >= HIGH_OVERLAP_THRESHOLD
            for selected_text, selected_tokens in selected_comparisons
        ):
            continue

        citation = f"[{len(passages) + 1}]"
        source_name = _source_name(chunk)
        block = _render_passage(citation, source_name, text)
        projected_context = "\n\n".join([*blocks, block])
        if len(projected_context) > max_characters:
            continue

        passages.append(
            ContextPassage(
                citation=citation,
                text=text,
                chunk_id=chunk.id,
                source_type=chunk.source_type,
                source_id=chunk.source_id,
                source_name=source_name,
                source_version=chunk.source_version,
                chunk_ordinal=chunk.ordinal,
                retrieval_rank=chunk.rank,
                retrieval_score=chunk.score,
                file_ids=tuple(chunk.file_ids),
                file_names=tuple(chunk.file_names),
            )
        )
        blocks.append(block)
        selected_comparisons.append((comparison, word_tokens))

    empty_reason: EmptyContextReason | None
    if passages:
        empty_reason = None
    elif not chunks:
        empty_reason = "no_results"
    elif not saw_usable_text:
        empty_reason = "no_usable_text"
    else:
        empty_reason = "budget_too_small"

    return _package(
        question=cleaned_question,
        blocks=blocks,
        passages=passages,
        max_characters=max_characters,
        empty_reason=empty_reason,
    )
