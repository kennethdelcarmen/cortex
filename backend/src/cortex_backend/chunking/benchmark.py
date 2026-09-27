"""Measured local FTS5 retrieval baseline for the checked-in fixture."""

from __future__ import annotations

import argparse
import asyncio
import os
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from time import perf_counter_ns

from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from ..storage import SQLiteStorage
from .evaluation import (
    DEFAULT_RECALL_K,
    EvaluationFixture,
    QueryEvaluation,
    evaluate_query,
    fixture_owner_id,
    load_fixture,
    seed_fixture,
)
from .models import ContentChunk
from .service import search_chunks


@dataclass(frozen=True)
class BenchmarkReport:
    """Aggregate quality and latency measurements for one benchmark run."""

    fixture_version: int
    source_count: int
    chunk_count: int
    query_count: int
    positive_query_count: int
    recall_at_k: int
    recall_at_k_value: float
    mean_reciprocal_rank: float
    negative_query_count: int
    negative_zero_result_count: int
    repetitions: int
    median_latency_ms: float
    p95_latency_ms: float


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        raise ValueError("cannot calculate a percentile without values")
    if not 0 < percentile <= 1:
        raise ValueError("percentile must be greater than 0 and at most 1")
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) * percentile) - 1)))
    return ordered[index]


async def run_benchmark(
    database_path: Path,
    fixture: EvaluationFixture,
    *,
    repetitions: int,
) -> BenchmarkReport:
    """Seed an isolated database and measure repeated retrieval calls."""

    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    storage = SQLiteStorage(database_path)
    await storage.check_ready()
    try:
        await seed_fixture(storage, fixture)
        evaluations: list[QueryEvaluation] = []
        latencies_ms: list[float] = []
        for query in fixture.queries:
            hits = await search_chunks(
                storage,
                fixture_owner_id(query.owner),
                query.query,
                source_types=query.source_types,
                limit=query.limit,
            )
            evaluations.append(evaluate_query(query, hits, recall_k=DEFAULT_RECALL_K))

            for _ in range(repetitions):
                started = perf_counter_ns()
                await search_chunks(
                    storage,
                    fixture_owner_id(query.owner),
                    query.query,
                    source_types=query.source_types,
                    limit=query.limit,
                )
                latencies_ms.append((perf_counter_ns() - started) / 1_000_000)

        async with storage.session() as db:
            chunk_count = int(await db.scalar(select(func.count(ContentChunk.id))) or 0)

        positive = [evaluation for evaluation in evaluations if evaluation.recall is not None]
        negative = [evaluation for evaluation in evaluations if evaluation.recall is None]
        recall = sum(evaluation.recall or 0 for evaluation in positive) / len(positive)
        mrr = sum(evaluation.reciprocal_rank or 0 for evaluation in positive) / len(positive)
        return BenchmarkReport(
            fixture_version=fixture.version,
            source_count=len(fixture.sources),
            chunk_count=chunk_count,
            query_count=len(evaluations),
            positive_query_count=len(positive),
            recall_at_k=DEFAULT_RECALL_K,
            recall_at_k_value=recall,
            mean_reciprocal_rank=mrr,
            negative_query_count=len(negative),
            negative_zero_result_count=sum(evaluation.zero_results for evaluation in negative),
            repetitions=repetitions,
            median_latency_ms=median(latencies_ms),
            p95_latency_ms=_percentile(latencies_ms, 0.95),
        )
    finally:
        await storage.close()


def format_report(report: BenchmarkReport) -> str:
    """Render one stable human-readable benchmark report."""

    return "\n".join(
        (
            "FTS retrieval baseline",
            f"fixture version: {report.fixture_version}",
            f"sources: {report.source_count} | chunks: {report.chunk_count}",
            f"queries: {report.query_count} | repetitions/query: {report.repetitions}",
            f"recall@{report.recall_at_k}: {report.recall_at_k_value:.3f} "
            f"({report.positive_query_count} positive queries)",
            f"mean reciprocal rank: {report.mean_reciprocal_rank:.3f}",
            f"negative queries with zero results: "
            f"{report.negative_zero_result_count}/{report.negative_query_count}",
            f"latency: median {report.median_latency_ms:.3f} ms | "
            f"p95 {report.p95_latency_ms:.3f} ms",
        )
    )


@contextmanager
def _database_environment(database_path: Path) -> Iterator[None]:
    previous = os.environ.get("CORTEX_DATABASE_PATH")
    os.environ["CORTEX_DATABASE_PATH"] = str(database_path)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("CORTEX_DATABASE_PATH", None)
        else:
            os.environ["CORTEX_DATABASE_PATH"] = previous


def _migrate(database_path: Path) -> None:
    backend_path = Path(__file__).resolve().parents[3]
    config = Config(str(backend_path / "alembic.ini"))
    with _database_environment(database_path):
        command.upgrade(config, "head")


def _default_fixture_path() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "tests"
        / "fixtures"
        / "retrieval"
        / "fts_baseline.json"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=_default_fixture_path())
    parser.add_argument("--repetitions", type=int, default=20)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    if args.repetitions < 1:
        raise SystemExit("--repetitions must be positive")
    fixture = load_fixture(args.fixture)
    with tempfile.TemporaryDirectory(prefix="cortex-fts-baseline-") as temporary_directory:
        database_path = Path(temporary_directory) / "cortex.db"
        _migrate(database_path)
        report = asyncio.run(
            run_benchmark(
                database_path,
                fixture,
                repetitions=args.repetitions,
            )
        )
    print(format_report(report))


if __name__ == "__main__":
    main()
