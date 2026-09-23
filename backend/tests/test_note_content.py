"""Canonical note HTML normalization behavior."""

import pytest

from cortex_backend.memory.content import html_to_text, normalize_note_body


def test_normalize_legacy_markdown_to_sanitized_html() -> None:
    body = normalize_note_body(
        "# Heading\n\n- [x] Finished\n- [ ] Next\n\n| A | B |\n| --- | --- |\n| one | two |"
    )

    assert body.startswith("<h1>Heading</h1>")
    assert 'checked=""' in body
    assert "<table>" in body
    assert html_to_text(body) == "Heading Finished Next A B one two"


def test_normalize_html_removes_unsafe_markup_and_urls() -> None:
    body = normalize_note_body(
        '<p onclick="alert(1)">Safe <strong>text</strong></p>'
        '<script>alert("xss")</script>'
        '<a href="javascript:alert(1)">bad link</a>'
        '<a href="https://example.com">good link</a>'
    )

    assert "onclick" not in body
    assert "script" not in body
    assert "javascript:" not in body
    assert 'href="https://example.com"' in body
    assert html_to_text(body) == "Safe text bad linkgood link"


@pytest.mark.parametrize("body", ["", "   ", "<p></p>", "<script>alert(1)</script>"])
def test_normalize_rejects_empty_body(body: str) -> None:
    with pytest.raises(ValueError, match="body must have content"):
        normalize_note_body(body)
