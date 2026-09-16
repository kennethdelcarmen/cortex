"""Typed HTTP response schemas."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class HealthResponse(BaseModel):
    status: str


class ApiMetadataResponse(BaseModel):
    service: str
    api_version: str


class ErrorResponse(BaseModel):
    code: str
    message: str


class SetupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    created_at: datetime


class CsrfResponse(BaseModel):
    csrf_token: str
