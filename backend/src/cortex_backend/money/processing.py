"""Restart-safe background processing for credit-card statement charges."""

from __future__ import annotations

import asyncio
import logging

from ..config import Settings
from ..storage import DatabaseStorage
from .service import process_due_installments, process_due_recurring_transactions

logger = logging.getLogger(__name__)


async def run_installment_charging_loop(
    storage: DatabaseStorage,
    settings: Settings,
) -> None:
    """Catch up due installment occurrences until application shutdown."""

    logger.info("Installment charging worker started")
    try:
        while True:
            try:
                processed = await process_due_installments(storage)
                logger.debug("Installment charging poll succeeded", extra={"processed": processed})
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Installment charging poll failed; retrying")
            await asyncio.sleep(settings.installment_charging_poll_seconds)
    except asyncio.CancelledError:
        logger.info("Installment charging worker stopped")
        raise


async def run_recurring_transaction_posting_loop(
    storage: DatabaseStorage,
    settings: Settings,
) -> None:
    """Catch up due recurring transaction occurrences until shutdown."""

    logger.info("Recurring transaction posting worker started")
    try:
        while True:
            try:
                result = await process_due_recurring_transactions(storage)
                logger.debug(
                    "Recurring transaction posting poll succeeded",
                    extra={
                        "processed": result.processed_count,
                        "failed": result.failed_count,
                    },
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Recurring transaction posting poll failed; retrying")
            await asyncio.sleep(settings.recurring_transaction_posting_poll_seconds)
    except asyncio.CancelledError:
        logger.info("Recurring transaction posting worker stopped")
        raise
