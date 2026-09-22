"""In-memory review/eval/model inventory for API (CI without Postgres)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any
from uuid import UUID, uuid4

from apps.api.store import CallStore, SessionRecord

# Seed taxonomy codes (mirrors db/schema.sql)
ROOT_CAUSE_CODES: frozenset[str] = frozenset(
    {
        "RC-ASR-ENT",
        "RC-ASR-NOISE",
        "RC-ASR-HALLU",
        "RC-ASR-DROP",
        "RC-TURN-EARLY",
        "RC-TURN-LATE",
        "RC-TURN-BARGE-MISS",
        "RC-TURN-BARGE-FALSE",
        "RC-LLM-INTENT",
        "RC-LLM-SLOT",
        "RC-LLM-HALLU",
        "RC-LLM-POLICY",
        "RC-LLM-REPAIR",
        "RC-TOOL-ARGS",
        "RC-TOOL-ERR",
        "RC-TTS-PRON",
        "RC-TTS-ARTIFACT",
        "RC-TTS-LAT",
        "RC-SYS-LAT",
        "RC-SYS-NET",
        "RC-SYS-OTHER",
    }
)


@dataclass
class LabelRecord:
    label_id: UUID
    call_id: UUID
    turn_id: UUID | None
    root_cause_code: str
    severity: int
    reviewer: str
    notes: str = ""
    add_to_dataset: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class EvalRunRecord:
    run_id: UUID
    dataset_id: UUID
    stack_version_id: UUID
    mode: str
    status: str = "queued"
    git_sha: str = "unknown"
    estimated_usd: float | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    metrics: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ModelVersionRecord:
    model_version_id: UUID
    component: str
    name: str
    revision: str
    owner: str
    status: str = "candidate"
    base_model: str | None = None
    license: str | None = None
    artifact_uri: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
    intended_use: str | None = None
    out_of_scope_use: str | None = None
    mlflow_run_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ReviewStore:
    """Extends call sessions with flags, labels, eval runs, and model inventory."""

    calls: CallStore
    audio_hmac_key: str = "callscope-audio-sign-dev"
    _labels: dict[UUID, list[LabelRecord]] = field(default_factory=dict)
    _flagged: dict[UUID, tuple[bool, list[str]]] = field(default_factory=dict)
    _root_causes: dict[UUID, list[str]] = field(default_factory=dict)
    _stack_label: dict[UUID, str] = field(default_factory=dict)
    _eval_runs: dict[UUID, EvalRunRecord] = field(default_factory=dict)
    _models: dict[UUID, ModelVersionRecord] = field(default_factory=dict)
    _exports: list[dict[str, Any]] = field(default_factory=list)
    _audit: list[dict[str, Any]] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock)

    def set_call_meta(
        self,
        call_id: UUID,
        *,
        flagged: bool = False,
        flag_reasons: list[str] | None = None,
        root_causes: list[str] | None = None,
        stack_label: str = "local-mac-dev",
    ) -> None:
        with self._lock:
            self._flagged[call_id] = (flagged, list(flag_reasons or []))
            self._root_causes[call_id] = list(root_causes or [])
            self._stack_label[call_id] = stack_label

    def list_calls(
        self,
        *,
        flagged: bool | None = None,
        root_cause: str | None = None,
        channel: str | None = None,
        stack_version_id: str | None = None,
        from_ts: datetime | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        _ = stack_version_id  # reserved; stack_label used on summaries
        sessions = self.calls.list_sessions()
        sessions.sort(key=lambda s: (s.started_at, str(s.call_id)), reverse=True)
        if cursor:
            past = False
            skipped: list[SessionRecord] = []
            for s in sessions:
                if past:
                    skipped.append(s)
                elif str(s.call_id) == cursor:
                    past = True
            sessions = skipped
        items: list[dict[str, Any]] = []
        for s in sessions:
            if channel and s.channel != channel:
                continue
            if from_ts and s.started_at < from_ts:
                continue
            fl, reasons = self._flagged.get(s.call_id, (False, []))
            if flagged is not None and fl != flagged:
                continue
            rcs = self._root_causes.get(s.call_id, [])
            if root_cause and root_cause not in rcs:
                continue
            items.append(self._summary(s, fl, reasons, rcs))
            if len(items) >= limit:
                break
        next_cursor = str(items[-1]["call_id"]) if len(items) == limit else None
        return items, next_cursor

    def call_detail(self, call_id: UUID) -> dict[str, Any] | None:
        rec = self.calls.get(call_id)
        if rec is None:
            return None
        fl, reasons = self._flagged.get(call_id, (False, []))
        rcs = self._root_causes.get(call_id, [])
        summary = self._summary(rec, fl, reasons, rcs)
        events = self.calls.events_for_call(call_id)
        labels = [self._label_dict(x) for x in self._labels.get(call_id, [])]
        tool_calls = [e for e in events if e.get("type") == "tool.call"]
        return {
            **summary,
            "turns": [],
            "events": events,
            "tool_calls": tool_calls,
            "labels": labels,
        }

    def _summary(
        self,
        s: SessionRecord,
        flagged: bool,
        reasons: list[str],
        root_causes: list[str],
    ) -> dict[str, Any]:
        dur = 0.0
        if s.ended_at and s.started_at:
            dur = (s.ended_at - s.started_at).total_seconds()
        return {
            "call_id": s.call_id,
            "started_at": s.started_at,
            "channel": s.channel,
            "stack_label": self._stack_label.get(s.call_id, "local-mac-dev"),
            "duration_s": dur,
            "flagged": flagged,
            "flag_reasons": reasons,
            "root_causes": root_causes,
        }

    def add_label(self, call_id: UUID, body: dict[str, Any]) -> LabelRecord | None:
        if self.calls.get(call_id) is None:
            return None
        code = str(body["root_cause_code"])
        if code not in ROOT_CAUSE_CODES:
            raise ValueError(f"unknown root_cause_code: {code}")
        lab = LabelRecord(
            label_id=uuid4(),
            call_id=call_id,
            turn_id=body.get("turn_id"),
            root_cause_code=code,
            severity=int(body["severity"]),
            reviewer=str(body["reviewer"]),
            notes=str(body.get("notes") or ""),
            add_to_dataset=body.get("add_to_dataset"),
        )
        with self._lock:
            self._labels.setdefault(call_id, []).append(lab)
            rcs = self._root_causes.setdefault(call_id, [])
            if code not in rcs:
                rcs.append(code)
            self._audit.append(
                {
                    "action": "label",
                    "call_id": str(call_id),
                    "label_id": str(lab.label_id),
                    "reviewer": lab.reviewer,
                    "at": datetime.now(UTC).isoformat(),
                }
            )
        return lab

    def _label_dict(self, lab: LabelRecord) -> dict[str, Any]:
        return {
            "label_id": lab.label_id,
            "turn_id": lab.turn_id,
            "root_cause_code": lab.root_cause_code,
            "severity": lab.severity,
            "reviewer": lab.reviewer,
            "notes": lab.notes,
            "add_to_dataset": lab.add_to_dataset,
            "created_at": lab.created_at,
        }

    def export_labelled(
        self, *, name: str, version: str, root_causes: list[str] | None = None
    ) -> UUID:
        dataset_id = uuid4()
        with self._lock:
            n = 0
            for _call_id, labs in self._labels.items():
                for lab in labs:
                    if root_causes and lab.root_cause_code not in root_causes:
                        continue
                    n += 1
            self._exports.append(
                {
                    "dataset_id": str(dataset_id),
                    "name": name,
                    "version": version,
                    "n_labels": n,
                }
            )
            self._audit.append(
                {
                    "action": "export_labelled",
                    "dataset_id": str(dataset_id),
                    "name": name,
                    "version": version,
                    "at": datetime.now(UTC).isoformat(),
                }
            )
        return dataset_id

    def sign_audio_url(self, call_id: UUID, *, ttl_s: int = 300) -> tuple[str, datetime] | None:
        rec = self.calls.get(call_id)
        if rec is None or not rec.recording_uri:
            return None
        expires = datetime.now(UTC) + timedelta(seconds=ttl_s)
        payload = {
            "call_id": str(call_id),
            "uri": rec.recording_uri,
            "exp": int(expires.timestamp()),
        }
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        sig = hmac.new(self.audio_hmac_key.encode(), raw, hashlib.sha256).digest()
        token = base64.urlsafe_b64encode(raw + b"." + sig).decode().rstrip("=")
        url = f"http://127.0.0.1:8000/v1/internal/audio?token={token}"
        return url, expires

    @staticmethod
    def verify_audio_token(token: str, audio_hmac_key: str) -> dict[str, Any] | None:
        try:
            pad = "=" * (-len(token) % 4)
            blob = base64.urlsafe_b64decode(token + pad)
            raw, sig = blob.rsplit(b".", 1)
            expect = hmac.new(audio_hmac_key.encode(), raw, hashlib.sha256).digest()
            if not hmac.compare_digest(sig, expect):
                return None
            data = json.loads(raw.decode())
            if int(data["exp"]) < int(datetime.now(UTC).timestamp()):
                return None
            if not isinstance(data, dict):
                return None
            return {str(k): v for k, v in data.items()}
        except (ValueError, KeyError, json.JSONDecodeError, TypeError):
            return None

    def create_eval_run(
        self, *, dataset_id: UUID, stack_version_id: UUID, mode: str
    ) -> EvalRunRecord:
        run = EvalRunRecord(
            run_id=uuid4(),
            dataset_id=dataset_id,
            stack_version_id=stack_version_id,
            mode=mode,
            status="queued",
            git_sha="api-queued",
            started_at=datetime.now(UTC),
            metrics=[],
        )
        with self._lock:
            self._eval_runs[run.run_id] = run
        return run

    def list_eval_runs(self) -> list[EvalRunRecord]:
        with self._lock:
            return list(self._eval_runs.values())

    def get_eval_run(self, run_id: UUID) -> EvalRunRecord | None:
        with self._lock:
            return self._eval_runs.get(run_id)

    def seed_eval_run(self, run: EvalRunRecord) -> None:
        with self._lock:
            self._eval_runs[run.run_id] = run

    def compare_runs(self, a: UUID, b: UUID) -> list[dict[str, Any]] | None:
        ra = self.get_eval_run(a)
        rb = self.get_eval_run(b)
        if ra is None or rb is None:
            return None
        by_key_a = {(m["metric"], m.get("slice", "all")): m for m in ra.metrics}
        out: list[dict[str, Any]] = []
        for m in rb.metrics:
            key = (m["metric"], m.get("slice", "all"))
            base = by_key_a.get(key)
            if base is None:
                continue
            delta = float(m["value"]) - float(base["value"])
            out.append(
                {
                    "metric": m["metric"],
                    "slice": m.get("slice", "all"),
                    "delta": delta,
                    "ci_low": delta - 0.01,
                    "ci_high": delta + 0.01,
                    "non_inferior": delta <= 0.01,
                }
            )
        return out

    def list_models(
        self, *, component: str | None = None, status: str | None = None
    ) -> list[ModelVersionRecord]:
        with self._lock:
            rows = list(self._models.values())
        if component:
            rows = [m for m in rows if m.component == component]
        if status:
            rows = [m for m in rows if m.status == status]
        return rows

    def register_model(self, body: dict[str, Any]) -> ModelVersionRecord:
        rec = ModelVersionRecord(
            model_version_id=uuid4(),
            component=str(body["component"]),
            name=str(body["name"]),
            revision=str(body["revision"]),
            owner=str(body["owner"]),
            base_model=body.get("base_model"),
            license=body.get("license"),
            artifact_uri=body.get("artifact_uri"),
            config=dict(body.get("config") or {}),
            intended_use=body.get("intended_use"),
            out_of_scope_use=body.get("out_of_scope_use"),
            mlflow_run_id=body.get("mlflow_run_id"),
        )
        with self._lock:
            self._models[rec.model_version_id] = rec
        return rec

    def get_model(self, model_version_id: UUID) -> ModelVersionRecord | None:
        with self._lock:
            return self._models.get(model_version_id)

    def transition_model(
        self, model_version_id: UUID, *, to: str, report_id: UUID | None = None
    ) -> ModelVersionRecord | None:
        _ = report_id
        with self._lock:
            m = self._models.get(model_version_id)
            if m is None:
                return None
            allowed = {
                "candidate": {"validated", "rejected"},
                "validated": {"production", "retired", "rejected"},
                "production": {"retired"},
                "retired": set(),
                "rejected": set(),
            }
            if to not in allowed.get(m.status, set()):
                raise ValueError(f"cannot transition {m.status} -> {to}")
            if to == "production":
                for other in self._models.values():
                    same = other.model_version_id == m.model_version_id
                    if other.status == "production" and not same:
                        other.status = "retired"
            m.status = to
            return m

    def seed_review_demo(self, *, n: int = 40, reviewer: str = "seed-demo") -> dict[str, Any]:
        """Create ``n`` synthetic calls with planted failures (and labels)."""
        from callscope.events.models import Event as EventModel
        from callscope.events.models import EventSource
        from callscope.review.seed_demo import build_seed_specs

        specs = build_seed_specs(n)
        created: list[str] = []
        labelled = 0
        for i, spec in enumerate(specs):
            rec = self.calls.create_session(
                consent_recording=True,
                consent_donate=False,
                policy_version="2026-09-20",
            )
            live = self.calls.get(rec.call_id)
            if live is not None:
                live.channel = spec.channel
            self.calls.end_session(rec.call_id, reason="seed")
            self.calls.register_recording(
                rec.call_id, mixed_uri=f"file:///tmp/seed-{rec.call_id}.wav"
            )
            self.set_call_meta(
                rec.call_id,
                flagged=spec.flagged,
                flag_reasons=list(spec.flag_reasons),
                root_causes=list(spec.root_causes),
                stack_label="seed-demo",
            )
            turn_id = uuid4()
            events = [
                EventModel(
                    event_id=uuid4(),
                    call_id=rec.call_id,
                    turn_id=turn_id,
                    t_ms=100,
                    ts=datetime.now(UTC),
                    source=EventSource.SIM,
                    type="stt.final",
                    payload={
                        "text": spec.transcript_caller,
                        "avg_conf": 0.4 if spec.flagged else 0.9,
                        "condition": spec.condition,
                    },
                ),
                EventModel(
                    event_id=uuid4(),
                    call_id=rec.call_id,
                    turn_id=turn_id,
                    t_ms=800,
                    ts=datetime.now(UTC),
                    source=EventSource.WORKER,
                    type="brain.first_token",
                    payload={"text": spec.transcript_agent},
                ),
            ]
            if "tool_error" in spec.flag_reasons:
                events.append(
                    EventModel(
                        event_id=uuid4(),
                        call_id=rec.call_id,
                        turn_id=turn_id,
                        t_ms=900,
                        ts=datetime.now(UTC),
                        source=EventSource.PLUGIN,
                        type="tool.call",
                        payload={"name": "book_slot", "args": {"phone": "555-0100"}},
                    )
                )
            self.calls.insert_events(events)
            # Pre-label planted failures so the demo starts with 30+ labels.
            if spec.planted_rc is not None and i < max(32, n):
                self.add_label(
                    rec.call_id,
                    {
                        "root_cause_code": spec.planted_rc,
                        "severity": spec.severity,
                        "reviewer": reviewer,
                        "notes": f"seed planted ({spec.condition})",
                        "add_to_dataset": "train" if i % 2 == 0 else "dev",
                    },
                )
                labelled += 1
            created.append(str(rec.call_id))
        with self._lock:
            self._audit.append(
                {
                    "action": "seed_review",
                    "n": n,
                    "labelled": labelled,
                    "at": datetime.now(UTC).isoformat(),
                }
            )
        return {"created": len(created), "labelled": labelled, "call_ids": created}
