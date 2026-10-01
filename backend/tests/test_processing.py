"""Supervised file-context worker tests."""

import asyncio
import sys
from contextlib import suppress
from pathlib import Path
from zipfile import ZipFile

import pytest

from cortex_backend.config import Settings
from cortex_backend.files import processing
from cortex_backend.files.processing import (
    FileProcessingHealth,
    ProcessingFailure,
    _extract_office_text_sync,
    processing_warnings,
    run_file_processing_loop,
)
from cortex_backend.money.processing import run_recurring_transaction_posting_loop
from cortex_backend.money.service import RecurringProcessResult


async def test_worker_retries_after_transient_poll_failure(monkeypatch) -> None:
    settings = Settings(file_processing_poll_seconds=0.001)
    health = FileProcessingHealth(enabled=True)
    recovered = asyncio.Event()
    calls = 0

    async def flaky_poll(*args, **kwargs) -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary database failure")
        recovered.set()
        return False

    monkeypatch.setattr(processing, "process_file_context_once", flaky_poll)
    task = asyncio.create_task(run_file_processing_loop(None, None, settings, health))
    try:
        await asyncio.wait_for(recovered.wait(), timeout=1)
        assert calls >= 2
        assert health.ready
        assert health.last_error is None
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    assert health.state == "stopped"


async def test_recurring_worker_retries_after_transient_poll_failure(monkeypatch) -> None:
    settings = Settings(recurring_transaction_posting_poll_seconds=0.001)
    recovered = asyncio.Event()
    calls = 0

    async def flaky_poll(*args, **kwargs) -> RecurringProcessResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary database failure")
        recovered.set()
        return RecurringProcessResult(processed_count=0, failed_count=0)

    monkeypatch.setattr(
        "cortex_backend.money.processing.process_due_recurring_transactions", flaky_poll
    )
    task = asyncio.create_task(run_recurring_transaction_posting_loop(None, settings))
    try:
        await asyncio.wait_for(recovered.wait(), timeout=1)
        assert calls >= 2
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def test_missing_processing_tools_are_reported_as_capability_warnings() -> None:
    settings = Settings(
        file_converter_command="missing-cortex-converter",
        file_ocr_command="missing-cortex-ocr",
    )

    assert processing_warnings(settings) == (
        "office_converter_unavailable",
        "ocr_unavailable",
    )


def test_capability_degradation_does_not_make_worker_unready() -> None:
    health = FileProcessingHealth(enabled=True)
    health.mark_started()
    health.mark_success(("ocr_unavailable",))

    assert health.ready
    assert health.state == "degraded"
    assert health.warnings == ("ocr_unavailable",)


def test_archive_office_fallbacks_extract_text(tmp_path: Path) -> None:
    fixtures = {
        "sample.docx": {
            "word/document.xml": (
                '<w:document xmlns:w="urn:w"><w:p><w:r><w:t>Doc text</w:t></w:r></w:p></w:document>'
            )
        },
        "sample.xlsx": {
            "xl/sharedStrings.xml": '<sst xmlns="urn:x"><si><t>Sheet text</t></si></sst>',
            "xl/worksheets/sheet1.xml": (
                '<worksheet xmlns="urn:x"><sheetData><row><c t="s"><v>0</v>'
                "</c></row></sheetData></worksheet>"
            ),
        },
        "sample.pptx": {
            "ppt/slides/slide1.xml": (
                '<p:sld xmlns:p="urn:p" xmlns:a="urn:a"><a:t>Slide text</a:t></p:sld>'
            )
        },
        "sample.odt": {
            "content.xml": (
                '<office:document-content xmlns:office="urn:office" xmlns:text="urn:text">'
                "<text:p>ODF text</text:p></office:document-content>"
            )
        },
    }

    for filename, members in fixtures.items():
        source = tmp_path / filename
        with ZipFile(source, "w") as archive:
            for name, content in members.items():
                archive.writestr(name, content)
        text = _extract_office_text_sync(source, source.suffix[1:])
        assert text.decode() in {"Doc text", "Sheet text", "Slide text", "ODF text"}


async def test_command_failure_logs_bounded_diagnostics(caplog) -> None:
    with pytest.raises(ProcessingFailure) as failure:
        await processing._run_command(
            [
                sys.executable,
                "-c",
                "import sys; print('diagnostic', file=sys.stderr); sys.exit(3)",
            ],
            1,
            "image_ocr_failed",
            missing_code="ocr_unavailable",
        )

    assert failure.value.code == "image_ocr_failed"
    assert caplog.records[-1].stderr == "diagnostic"


async def test_command_timeout_is_reported_as_retryable_failure() -> None:
    with pytest.raises(ProcessingFailure) as failure:
        await processing._run_command(
            [sys.executable, "-c", "import time; time.sleep(1)"],
            0.01,
            "office_conversion_failed",
            missing_code="office_converter_unavailable",
        )

    assert failure.value.code == "office_conversion_failed"
    assert failure.value.retryable
