"""Deterministic source normalization and hybrid character chunking."""

from __future__ import annotations

import re
import unicodedata
from html.parser import HTMLParser

DEFAULT_CHUNK_SIZE = 1_200
DEFAULT_CHUNK_OVERLAP = 200

_MULTIPLE_BLANK_LINES = re.compile(r"\n{3,}")
_SENTENCE_END = re.compile(r"[.!?。！？](?:\s|$)")


def normalize_source_text(value: str) -> str:
    """Normalize Unicode, line endings, and incidental trailing whitespace."""

    normalized = unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
    normalized = "\n".join(line.rstrip() for line in normalized.split("\n"))
    normalized = _MULTIPLE_BLANK_LINES.sub("\n\n", normalized)
    return normalized.strip()


class _BlockTextParser(HTMLParser):
    """Extract visible HTML text while retaining block-level boundaries."""

    _BLOCK_TAGS = {
        "blockquote",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "ol",
        "p",
        "pre",
        "table",
        "tbody",
        "td",
        "th",
        "thead",
        "tr",
        "ul",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._blocks: list[str] = []

    def _finish_block(self) -> None:
        block = " ".join("".join(self._parts).split())
        if block:
            self._blocks.append(block)
        self._parts.clear()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag == "br":
            self._finish_block()
        elif tag in self._BLOCK_TAGS:
            self._finish_block()
            if tag == "li":
                self._parts.append("- ")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in {"br", "hr"}:
            self._finish_block()

    def handle_endtag(self, tag: str) -> None:
        if tag in self._BLOCK_TAGS:
            self._finish_block()

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def finish(self) -> str:
        self._finish_block()
        return normalize_source_text("\n\n".join(self._blocks))


def html_to_chunk_text(value: str) -> str:
    """Return visible note text with headings, paragraphs, and lists separated."""

    parser = _BlockTextParser()
    parser.feed(value)
    parser.close()
    return parser.finish()


def _preferred_break(value: str, start: int, limit: int) -> int:
    """Choose the latest useful semantic boundary before a hard limit."""

    minimum = start + max(1, (limit - start) // 2)
    paragraph = value.rfind("\n\n", minimum, limit)
    if paragraph > start:
        return paragraph

    line = value.rfind("\n", minimum, limit)
    if line > start:
        return line

    sentence_end = start
    for match in _SENTENCE_END.finditer(value, start, limit):
        sentence_end = match.end()
    if sentence_end > start:
        return sentence_end

    whitespace = max(
        (index for index in range(minimum, limit) if value[index].isspace()),
        default=-1,
    )
    return whitespace if whitespace > start else limit


def chunk_text(
    value: str,
    *,
    max_characters: int = DEFAULT_CHUNK_SIZE,
    overlap_characters: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """Split normalized text into bounded, overlapping semantic chunks."""

    if max_characters < 1 or overlap_characters < 0 or overlap_characters >= max_characters:
        raise ValueError("invalid chunk size or overlap")

    normalized = normalize_source_text(value)
    if not normalized:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        remaining = len(normalized) - start
        if remaining <= max_characters:
            chunk = normalized[start:].strip()
            if chunk:
                chunks.append(chunk)
            break

        limit = min(start + max_characters, len(normalized))
        end = _preferred_break(normalized, start, limit)
        if end <= start:
            end = limit
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)

        next_start = max(start + 1, end - overlap_characters)
        while next_start < len(normalized) and normalized[next_start].isspace():
            next_start += 1
        start = max(next_start, end) if next_start <= start else next_start

    return chunks
