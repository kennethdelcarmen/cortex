"""Canonical HTML note-content normalization and text extraction."""

from __future__ import annotations

import re
from html.parser import HTMLParser

import nh3
from markdown_it import MarkdownIt

MAX_NOTE_BODY_LENGTH = 100_000

_HTML_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9-]*(?:\s+[^>]*)?\s*/?>")

NOTE_HTML_TAGS = {
    "a",
    "br",
    "blockquote",
    "code",
    "div",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "input",
    "label",
    "li",
    "ol",
    "p",
    "pre",
    "s",
    "span",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "u",
    "ul",
}

NOTE_HTML_ATTRIBUTES = {
    "*": {"data-checked", "data-type"},
    "a": {"href", "target", "title"},
    "input": {"checked", "disabled", "type"},
    "li": {"data-checked", "data-type"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
}

_MARKDOWN = MarkdownIt("gfm-like2", {"html": False})
_HTML_CLEANER = nh3.Cleaner(
    tags=NOTE_HTML_TAGS,
    attributes=NOTE_HTML_ATTRIBUTES,
    url_schemes={"http", "https", "mailto"},
    link_rel="noopener noreferrer",
    strip_comments=True,
)


class _PlainTextParser(HTMLParser):
    """Extract visible note text for validation, previews, and FTS."""

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
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br" or tag in self._BLOCK_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._BLOCK_TAGS:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(value: str) -> str:
    """Return normalized visible text from canonical HTML."""

    parser = _PlainTextParser()
    parser.feed(value)
    parser.close()
    return " ".join("".join(parser.parts).split())


def sanitize_note_html(value: str) -> str:
    """Sanitize a note HTML fragment to the supported editor subset."""

    return _HTML_CLEANER.clean(value).strip()


def _looks_like_note_html(value: str) -> bool:
    return bool(_HTML_TAG.search(value))


def normalize_note_body(value: str) -> str:
    """Normalize HTML or legacy Markdown into non-empty canonical HTML."""

    source = value.strip()
    if not source:
        raise ValueError("body must have content")

    rendered = source if _looks_like_note_html(source) else _MARKDOWN.render(source)
    cleaned = sanitize_note_html(rendered)
    if not html_to_text(cleaned):
        raise ValueError("body must have content")
    if len(cleaned) > MAX_NOTE_BODY_LENGTH:
        raise ValueError(
            f"body must be at most {MAX_NOTE_BODY_LENGTH} characters after normalization"
        )
    return cleaned
