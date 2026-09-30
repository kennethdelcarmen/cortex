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
from typing import Literal

from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from ..config import Settings
from ..embeddings.provider import EmbeddingProvider, LocalEmbeddingProvider
from ..embeddings.service import process_embeddings_once
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
class RetrievalMetrics:
    """Quality and latency measurements for one retrieval channel."""

    recall_at_k_value: float
    mean_reciprocal_rank: float
    median_latency_ms: float
    p95_latency_ms: float


@dataclass(frozen=True)
class BenchmarkReport:
    """Aggregate quality and latency measurements for one benchmark run."""

    fixture_version: int
    source_count: int
    chunk_count: int
    query_count: int
    positive_query_count: int
    recall_at_k: int
    negative_query_count: int
    negative_zero_result_count: int
    repetitions: int
    lexical: RetrievalMetrics
    vector: RetrievalMetrics | None
    hybrid: RetrievalMetrics | None


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
    embedding_provider: EmbeddingProvider | None = None,
) -> BenchmarkReport:
    """Seed an isolated database and measure retrieval channels."""

    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    storage = SQLiteStorage(database_path, sqlite_vec_enabled=embedding_provider is not None)
    await storage.check_ready()
    try:
        await seed_fixture(storage, fixture)
        if embedding_provider is not None:
            settings = Settings(
                database_path=database_path,
                embeddings_enabled=True,
                embedding_batch_size=32,
            )
            while await process_embeddings_once(storage, embedding_provider, settings):
                pass

        channel_evaluations: dict[str, list[QueryEvaluation]] = {"lexical": []}
        channel_latencies: dict[str, list[float]] = {"lexical": []}
        if embedding_provider is not None:
            channel_evaluations.update({"vector": [], "hybrid": []})
            channel_latencies.update({"vector": [], "hybrid": []})
        for query in fixture.queries:
            owner_id = fixture_owner_id(query.owner)
            lexical_hits = await search_chunks(
                storage,
                owner_id,
                query.query,
                source_types=query.source_types,
                limit=query.limit,
                retrieval_mode="lexical",
            )
            channel_evaluations["lexical"].append(
                evaluate_query(query, lexical_hits, recall_k=DEFAULT_RECALL_K)
            )

            for _ in range(repetitions):
                started = perf_counter_ns()
                await search_chunks(
                    storage,
                    owner_id,
                    query.query,
                    source_types=query.source_types,
                    limit=query.limit,
                    retrieval_mode="lexical",
                )
                channel_latencies["lexical"].append((perf_counter_ns() - started) / 1_000_000)

            if embedding_provider is not None:
                semantic_query = query.semantic_query or query.query
                for channel in ("vector", "hybrid"):
                    mode: Literal["vector", "hybrid"] = (
                        "vector" if channel == "vector" else "hybrid"
                    )
                    semantic_hits = await search_chunks(
                        storage,
                        owner_id,
                        semantic_query,
                        source_types=query.source_types,
                        limit=query.limit,
                        embedding_provider=embedding_provider,
                        retrieval_mode=mode,
                    )
                    channel_evaluations[channel].append(
                        evaluate_query(query, semantic_hits, recall_k=DEFAULT_RECALL_K)
                    )
                    for _ in range(repetitions):
                        started = perf_counter_ns()
                        await search_chunks(
                            storage,
                            owner_id,
                            semantic_query,
                            source_types=query.source_types,
                            limit=query.limit,
                            embedding_provider=embedding_provider,
                            retrieval_mode=mode,
                        )
                        channel_latencies[channel].append((perf_counter_ns() - started) / 1_000_000)

        async with storage.session() as db:
            chunk_count = int(await db.scalar(select(func.count(ContentChunk.id))) or 0)

        lexical_evaluations = channel_evaluations["lexical"]
        negative = [evaluation for evaluation in lexical_evaluations if evaluation.recall is None]

        def metrics(channel: str) -> RetrievalMetrics:
            evaluations = channel_evaluations[channel]
            positive = [evaluation for evaluation in evaluations if evaluation.recall is not None]
            latencies = channel_latencies[channel]
            return RetrievalMetrics(
                recall_at_k_value=sum(evaluation.recall or 0 for evaluation in positive)
                / len(positive),
                mean_reciprocal_rank=sum(evaluation.reciprocal_rank or 0 for evaluation in positive)
                / len(positive),
                median_latency_ms=median(latencies),
                p95_latency_ms=_percentile(latencies, 0.95),
            )

        return BenchmarkReport(
            fixture_version=fixture.version,
            source_count=len(fixture.sources),
            chunk_count=chunk_count,
            query_count=len(lexical_evaluations),
            positive_query_count=len(lexical_evaluations) - len(negative),
            recall_at_k=DEFAULT_RECALL_K,
            negative_query_count=len(negative),
            negative_zero_result_count=sum(evaluation.zero_results for evaluation in negative),
            repetitions=repetitions,
            lexical=metrics("lexical"),
            vector=metrics("vector") if embedding_provider is not None else None,
            hybrid=metrics("hybrid") if embedding_provider is not None else None,
        )
    finally:
        await storage.close()


def format_report(report: BenchmarkReport) -> str:
    """Render one stable human-readable benchmark report."""

    lines = [
        "Retrieval benchmark",
        f"fixture version: {report.fixture_version}",
        f"sources: {report.source_count} | chunks: {report.chunk_count}",
        f"queries: {report.query_count} | repetitions/query: {report.repetitions}",
        f"positive queries: {report.positive_query_count} | "
        f"negative queries with zero results: "
        f"{report.negative_zero_result_count}/{report.negative_query_count}",
    ]
    for name, metrics in (
        ("lexical", report.lexical),
        ("vector", report.vector),
        ("hybrid", report.hybrid),
    ):
        if metrics is None:
            continue
        lines.extend(
            (
                f"{name}: recall@{report.recall_at_k} {metrics.recall_at_k_value:.3f} | "
                f"MRR {metrics.mean_reciprocal_rank:.3f}",
                f"{name} latency: median {metrics.median_latency_ms:.3f} ms | "
                f"p95 {metrics.p95_latency_ms:.3f} ms",
            )
        )
    return "\n".join(lines)


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
    parser.add_argument(
        "--semantic",
        action="store_true",
        help="also measure local FastEmbed vector and hybrid retrieval",
    )
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
                embedding_provider=(
                    LocalEmbeddingProvider(Path("data/models")) if args.semantic else None
                ),
            )
        )
    print(format_report(report))


if __name__ == "__main__":
    main()
