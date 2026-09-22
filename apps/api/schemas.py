"""API schemas aligned with docs/api/openapi.yaml (T-M1-07 subset)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class StatusOut(BaseModel):
    state: Literal["online", "warming_up", "offline"]
    active_calls: int
    max_concurrent: int
    stack_label: str
    next_window: datetime | None = None


class SessionRequest(BaseModel):
    consent_recording: Literal[True]
    consent_donate: bool = False
    policy_version: str = Field(min_length=1)


class SessionResponse(BaseModel):
    call_id: UUID
    livekit_url: str
    room: str
    token: str
    expires_at: datetime
    max_duration_s: int


class EventIn(BaseModel):
    event_id: UUID
    call_id: UUID
    turn_id: UUID | None = None
    t_ms: int
    ts: datetime
    source: Literal["worker", "plugin", "client", "sim"]
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class EventsBatchRequest(BaseModel):
    events: list[EventIn] = Field(max_length=500)


class EventsBatchResponse(BaseModel):
    accepted: int
    duplicates: int


class RecordingRegisterRequest(BaseModel):
    mixed_uri: str = Field(min_length=1)
    caller_uri: str | None = None
    agent_uri: str | None = None


class CallSummaryOut(BaseModel):
    call_id: UUID
    started_at: datetime
    channel: str
    stack_label: str
    duration_s: float
    flagged: bool
    flag_reasons: list[str]
    root_causes: list[str]


class CallListOut(BaseModel):
    items: list[CallSummaryOut]
    next_cursor: str | None = None


class LabelRequest(BaseModel):
    turn_id: UUID | None = None
    root_cause_code: str
    severity: int = Field(ge=1, le=4)
    reviewer: str
    notes: str = ""
    add_to_dataset: Literal["train", "dev"] | None = None


class LabelOut(LabelRequest):
    label_id: UUID
    created_at: datetime


class CallDetailOut(CallSummaryOut):
    turns: list[dict[str, Any]] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    labels: list[LabelOut] = Field(default_factory=list)


class AudioUrlOut(BaseModel):
    url: str
    expires_at: datetime


class ExportLabelledRequest(BaseModel):
    name: str
    version: str
    root_causes: list[str] | None = None


class ExportLabelledOut(BaseModel):
    dataset_id: UUID


class EvalRunCreate(BaseModel):
    dataset_id: UUID
    stack_version_id: UUID
    mode: Literal["stage_replay", "text_replay", "caller_sim", "baseline"]


class EvalRunOut(BaseModel):
    run_id: UUID
    dataset_id: UUID
    stack_version_id: UUID
    mode: str
    status: str
    git_sha: str
    estimated_usd: float | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class MetricOut(BaseModel):
    metric: str
    slice: str = "all"
    value: float
    ci_low: float
    ci_high: float
    n: int


class EvalRunDetailOut(EvalRunOut):
    metrics: list[MetricOut] = Field(default_factory=list)


class CompareDeltaOut(BaseModel):
    metric: str
    slice: str
    delta: float
    ci_low: float
    ci_high: float
    non_inferior: bool


class ModelVersionCreate(BaseModel):
    component: Literal["asr", "tts", "llm", "vad", "turn_detector", "judge"]
    name: str
    revision: str
    owner: str
    base_model: str | None = None
    license: str | None = None
    artifact_uri: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    intended_use: str | None = None
    out_of_scope_use: str | None = None
    mlflow_run_id: str | None = None


class ModelVersionOut(ModelVersionCreate):
    model_version_id: UUID
    status: Literal["candidate", "validated", "production", "retired", "rejected"]
    created_at: datetime


class ModelTransitionRequest(BaseModel):
    to: Literal["validated", "production", "retired", "rejected"]
    report_id: UUID | None = None
    rationale: str | None = None
    report_passed: bool | None = None
    monitoring_on: bool = True
    rollback_stack_id: str | None = None


class ValidationReportOut(BaseModel):
    report_id: UUID
    model_version_id: UUID
    eval_run_id: UUID
    thresholds: dict[str, Any]
    results: dict[str, Any]
    passed: bool
    report_uri: str
    signed_off_by: str | None = None
