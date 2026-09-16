"""Typed HTTP response schemas."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class ApiMetadataResponse(BaseModel):
    service: str
    api_version: str


class ErrorResponse(BaseModel):
    code: str
    message: str
