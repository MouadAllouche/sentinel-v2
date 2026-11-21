"""Pydantic request/response models for the API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MitreTag(StrictModel):
    """A static MITRE technique reference. Always indicative, never a confirmation."""

    id: str
    name: str
    tactic: str
    url: str
    label: str


class IncidentOut(BaseModel):
    """Incident response shape; additional engine fields are preserved."""

    model_config = ConfigDict(extra="allow")

    id: int
    title: str
    status: str
    severity: str
    mitre: list[MitreTag] = Field(default_factory=list)


class IncidentPage(BaseModel):
    items: list[IncidentOut]
    next_cursor: str | None = None
    total: int | None = None


class LoginRequest(StrictModel):
    username: str
    password: str


class PasswordChange(StrictModel):
    old_password: str
    new_password: str


class ErrorDetail(StrictModel):
    path: str
    message: str


class ErrorBody(StrictModel):
    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)


class ErrorResponse(StrictModel):
    error: ErrorBody


class BulkStatusChange(StrictModel):
    ids: list[int]
    status: str
    reason: str | None = None


class StatusChange(StrictModel):
    status: str
    reason: str | None = None
    updated_at: str | None = None


class NoteCreate(StrictModel):
    body: str


class AssigneeUpdate(StrictModel):
    assignee: str


class RuleDefinition(StrictModel):
    model_config = ConfigDict(extra="forbid")

    definition: dict[str, Any]


class ReapplyRequest(StrictModel):
    filters: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = True


class BaselineAccept(StrictModel):
    path: str
    reason: str = Field(min_length=5)
