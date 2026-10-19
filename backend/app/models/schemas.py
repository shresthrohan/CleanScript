"""Pydantic request/response models for the REST API (contract documented in docs/API.md)."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app import config


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
    request_id: Optional[str] = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


class SessionResponse(BaseModel):
    session_id: str
    filename: str
    profile: dict[str, Any]
    limits: dict[str, int]


class CompileRequest(BaseModel):
    source: str = Field(..., max_length=config.MAX_SOURCE_CHARS)


class CompileResponse(BaseModel):
    compilation_id: str
    session_id: str
    status: Literal["success", "failed"]
    stages: dict[str, str]
    tokens: Optional[list[dict[str, Any]]]
    ast: Optional[dict[str, Any]]
    semantic: Optional[dict[str, Any]]
    ir: Optional[dict[str, Any]]
    generated_code: Optional[str]
    diagnostics: list[dict[str, Any]]


class ExecuteRequest(BaseModel):
    compilation_id: str = Field(..., min_length=1, max_length=64)


class ExecutionResponse(BaseModel):
    status: Literal["success", "failed"]
    session_id: str
    compilation_id: str
    result_id: Optional[str]
    output_filename: Optional[str]
    operations: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    error: Optional[dict[str, Any]]
    before: dict[str, int]
    after: Optional[dict[str, int]]
    result_profile: Optional[dict[str, Any]]
