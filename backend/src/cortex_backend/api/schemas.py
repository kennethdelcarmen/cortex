"""Typed HTTP response schemas."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, model_validator


class HealthResponse(BaseModel):
    status: str
    warnings: list[str] = Field(default_factory=list)


class ApiMetadataResponse(BaseModel):
    service: str
    api_version: str


class ErrorResponse(BaseModel):
    code: str
    message: str
    unknown_tags: list[str] | None = None
    allowed_tags: list[str] | None = None


class SetupRequest(BaseModel):
    email: EmailStr
    display_name: str | None = Field(default=None, max_length=80)
    password: str = Field(min_length=12, max_length=128)
    mcp_api_key: str | None = Field(default=None, min_length=32, max_length=256)
    use_setup_secret_as_mcp_key: bool = False

    @model_validator(mode="after")
    def require_one_mcp_credential_source(self) -> "SetupRequest":
        if (self.mcp_api_key is not None) == self.use_setup_secret_as_mcp_key:
            raise ValueError("Choose exactly one of mcp_api_key or use_setup_secret_as_mcp_key.")
        return self


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class ProfileUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    display_name: str | None
    created_at: datetime


class CsrfResponse(BaseModel):
    csrf_token: str


class McpApiKeyUpdateRequest(BaseModel):
    key: str = Field(min_length=32, max_length=256)


class McpApiKeyResponse(BaseModel):
    configured: bool
    revoked: bool
    created_at: datetime | None
    updated_at: datetime | None
    revoked_at: datetime | None
