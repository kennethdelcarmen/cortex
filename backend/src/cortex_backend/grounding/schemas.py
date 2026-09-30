"""MCP transport contracts for grounded question preparation."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..chunking.context import EmptyContextReason
from ..chunking.service import ChunkSourceType


class GroundedCitationResponse(BaseModel):
    """One citation-bearing passage exposed to an external agent."""

    citation: str
    text: str
    chunk_id: str
    source_type: ChunkSourceType
    source_id: str
    source_name: str
    source_version: str
    chunk_ordinal: int = Field(ge=0)
    retrieval_rank: int = Field(ge=1)
    retrieval_score: float = Field(
        description="Final lexical or hybrid retrieval score; higher is better."
    )
    file_ids: list[str]
    file_names: list[str]


class GroundedQuestionResponse(BaseModel):
    """Structured grounded prompt package returned by the MCP tool."""

    question: str
    prompt: str | None
    context_text: str
    citations: list[GroundedCitationResponse]
    has_context: bool
    empty_reason: EmptyContextReason | None
    message: str | None
