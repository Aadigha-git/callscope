"""SQLAlchemy 2 models for core CallScope tables (schema ``cs``).

Enums/types are created by ``db/schema.sql`` / Alembic baseline; ORM uses
``create_type=False`` so metadata does not try to recreate them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _enum(name: str, *values: str) -> Enum:
    return Enum(*values, name=name, schema="cs", create_type=False, native_enum=True)


component_kind = _enum("component_kind", "asr", "tts", "llm", "vad", "turn_detector", "judge")
model_status = _enum("model_status", "candidate", "validated", "production", "retired", "rejected")
call_channel = _enum("call_channel", "browser", "sip", "sim", "replay")
speaker_kind = _enum("speaker", "caller", "agent")


class ModelVersion(Base):
    __tablename__ = "model_versions"
    __table_args__ = (
        UniqueConstraint("component", "name", "revision"),
        {"schema": "cs"},
    )

    model_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=sa_text("gen_random_uuid()")
    )
    component: Mapped[str] = mapped_column(component_kind, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    base_model: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[str] = mapped_column(Text, nullable=False)
    license: Mapped[str | None] = mapped_column(Text)
    artifact_uri: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'{}'")
    )
    config_sha256: Mapped[str | None] = mapped_column(Text)
    training_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    intended_use: Mapped[str | None] = mapped_column(Text)
    out_of_scope_use: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        model_status, nullable=False, server_default=sa_text("'candidate'")
    )
    mlflow_run_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa_text("now()")
    )


class StackVersion(Base):
    __tablename__ = "stack_versions"
    __table_args__ = {"schema": "cs"}

    stack_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=sa_text("gen_random_uuid()")
    )
    label: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    asr_mv: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cs.model_versions.model_version_id"), nullable=False
    )
    tts_mv: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cs.model_versions.model_version_id"), nullable=False
    )
    llm_mv: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cs.model_versions.model_version_id"), nullable=False
    )
    vad_mv: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cs.model_versions.model_version_id")
    )
    turn_mv: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cs.model_versions.model_version_id")
    )
    hermes_version: Mapped[str] = mapped_column(Text, nullable=False)
    plugin_version: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    worker_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    git_sha: Mapped[str] = mapped_column(Text, nullable=False)
    is_production: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa_text("now()")
    )


class Call(Base):
    __tablename__ = "calls"
    __table_args__ = {"schema": "cs"}

    call_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=sa_text("gen_random_uuid()")
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    channel: Mapped[str] = mapped_column(call_channel, nullable=False)
    stack_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cs.stack_versions.stack_version_id"), nullable=False
    )
    scenario_id: Mapped[str | None] = mapped_column(Text)
    is_synthetic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_text("false")
    )
    consent_recording: Mapped[bool] = mapped_column(Boolean, nullable=False)
    consent_donate: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_text("false")
    )
    consent_policy_v: Mapped[str] = mapped_column(Text, nullable=False)
    recording_uri: Mapped[str | None] = mapped_column(Text)
    raw_purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_reason: Mapped[str | None] = mapped_column(Text)
    flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_text("false"))
    flag_reasons: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=sa_text("'{}'")
    )

    turns: Mapped[list[Turn]] = relationship(back_populates="call", cascade="all, delete-orphan")
    events: Mapped[list[Event]] = relationship(back_populates="call", cascade="all, delete-orphan")
    tool_calls: Mapped[list[ToolCall]] = relationship(
        back_populates="call", cascade="all, delete-orphan"
    )


class Turn(Base):
    __tablename__ = "turns"
    __table_args__ = (UniqueConstraint("call_id", "idx"), {"schema": "cs"})

    turn_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=sa_text("gen_random_uuid()")
    )
    call_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cs.calls.call_id", ondelete="CASCADE"), nullable=False
    )
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[str] = mapped_column(speaker_kind, nullable=False)
    t_start_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    t_end_ms: Mapped[int | None] = mapped_column(BigInteger)
    text: Mapped[str | None] = mapped_column(Text)
    asr_avg_conf: Mapped[float | None] = mapped_column(Float)
    interrupted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa_text("false")
    )
    spoken_prefix: Mapped[str | None] = mapped_column(Text)

    call: Mapped[Call] = relationship(back_populates="turns")


class Event(Base):
    __tablename__ = "events"
    __table_args__ = {"schema": "cs"}

    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    call_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cs.calls.call_id", ondelete="CASCADE"), nullable=False
    )
    turn_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cs.turns.turn_id", ondelete="SET NULL")
    )
    t_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'{}'")
    )

    call: Mapped[Call] = relationship(back_populates="events")


class ToolCall(Base):
    __tablename__ = "tool_calls"
    __table_args__ = {"schema": "cs"}

    tool_call_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=sa_text("gen_random_uuid()")
    )
    call_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cs.calls.call_id", ondelete="CASCADE"), nullable=False
    )
    turn_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cs.turns.turn_id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    args: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    args_scrubbed: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    policy_rule: Mapped[str | None] = mapped_column(Text)
    mutating: Mapped[bool] = mapped_column(Boolean, nullable=False)
    confirmed: Mapped[bool | None] = mapped_column(Boolean)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)

    call: Mapped[Call] = relationship(back_populates="tool_calls")


class RootCauseCode(Base):
    __tablename__ = "root_cause_codes"
    __table_args__ = {"schema": "cs"}

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


dataset_kind = _enum("dataset_kind", "synthetic", "recorded", "labelled_failures", "mixed")
split_name = _enum("split_name", "train", "dev", "test")


class DatasetItem(Base):
    __tablename__ = "dataset_items"
    __table_args__ = {"schema": "cs"}

    item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=sa_text("gen_random_uuid()")
    )
    dataset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cs.datasets.dataset_id", ondelete="CASCADE"),
        nullable=False,
    )
    split: Mapped[str] = mapped_column(split_name, nullable=False)
    scenario_id: Mapped[str] = mapped_column(Text, nullable=False)
    variant: Mapped[str | None] = mapped_column(Text)
    turn_idx: Mapped[int | None] = mapped_column(Integer)
    audio_uri: Mapped[str] = mapped_column(Text, nullable=False)
    audio_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    condition_code: Mapped[str] = mapped_column(Text, nullable=False)
    voice_profile: Mapped[str | None] = mapped_column(Text)
    augmentation: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa_text("'{}'")
    )
    ref_transcript: Mapped[str | None] = mapped_column(Text)
    ref_intent: Mapped[str | None] = mapped_column(Text)
    ref_slots: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ref_expected: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    source_call_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cs.calls.call_id")
    )

    dataset: Mapped[Dataset] = relationship(back_populates="items")


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (
        UniqueConstraint("name", "version"),
        {"schema": "cs"},
    )

    dataset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=sa_text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(dataset_kind, nullable=False)
    manifest_uri: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    n_items: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_dataset_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cs.datasets.dataset_id")
    )
    dq_report: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    dq_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    frozen: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa_text("now()")
    )

    items: Mapped[list[DatasetItem]] = relationship(back_populates="dataset")
