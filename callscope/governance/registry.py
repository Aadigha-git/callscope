"""In-memory / file-backed model + stack registry (T-M5-01).

Mirrors ``cs.model_versions`` / ``cs.stack_versions``. Postgres ORM remains available;
this store keeps CI and local demos working without a live DB (same pattern as
FileEvalStore / ReviewStore).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import UUID, uuid4

COMPONENT_KINDS = frozenset({"asr", "tts", "llm", "vad", "turn_detector", "judge"})
MODEL_STATUSES = frozenset({"candidate", "validated", "production", "retired", "rejected"})


def config_sha256(config: dict[str, Any]) -> str:
    raw = json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


@dataclass(slots=True)
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
    config_sha256: str | None = None
    training_data: dict[str, Any] | None = None
    intended_use: str | None = None
    out_of_scope_use: str | None = None
    mlflow_run_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["model_version_id"] = str(self.model_version_id)
        d["created_at"] = self.created_at.isoformat()
        return d


@dataclass(slots=True)
class StackVersionRecord:
    stack_version_id: UUID
    label: str
    asr_mv: UUID
    tts_mv: UUID
    llm_mv: UUID
    hermes_version: str
    plugin_version: str
    prompt_sha256: str
    worker_config: dict[str, Any]
    git_sha: str
    vad_mv: UUID | None = None
    turn_mv: UUID | None = None
    is_production: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["stack_version_id"] = str(self.stack_version_id)
        for key in ("asr_mv", "tts_mv", "llm_mv", "vad_mv", "turn_mv"):
            val = getattr(self, key)
            d[key] = str(val) if val is not None else None
        d["created_at"] = self.created_at.isoformat()
        return d


class RegistryError(ValueError):
    """Invalid registration / transition / uniqueness violation."""


@dataclass
class ModelStackRegistry:
    """Thread-safe registry with optional JSON persistence."""

    root: Path | None = None
    _models: dict[UUID, ModelVersionRecord] = field(default_factory=dict)
    _stacks: dict[UUID, StackVersionRecord] = field(default_factory=dict)
    _by_key: dict[tuple[str, str, str], UUID] = field(default_factory=dict)
    _by_label: dict[str, UUID] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def __post_init__(self) -> None:
        if self.root is not None:
            self.root.mkdir(parents=True, exist_ok=True)
            self._load()

    def _path(self) -> Path | None:
        return None if self.root is None else self.root / "registry.json"

    def _persist(self) -> None:
        path = self._path()
        if path is None:
            return
        payload = {
            "models": [m.to_dict() for m in self._models.values()],
            "stacks": [s.to_dict() for s in self._stacks.values()],
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _load(self) -> None:
        path = self._path()
        if path is None or not path.is_file():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        for row in data.get("models") or []:
            mid = UUID(str(row["model_version_id"]))
            model = ModelVersionRecord(
                model_version_id=mid,
                component=str(row["component"]),
                name=str(row["name"]),
                revision=str(row["revision"]),
                owner=str(row["owner"]),
                status=str(row.get("status") or "candidate"),
                base_model=row.get("base_model"),
                license=row.get("license"),
                artifact_uri=row.get("artifact_uri"),
                config=dict(row.get("config") or {}),
                config_sha256=row.get("config_sha256"),
                training_data=row.get("training_data"),
                intended_use=row.get("intended_use"),
                out_of_scope_use=row.get("out_of_scope_use"),
                mlflow_run_id=row.get("mlflow_run_id"),
                created_at=datetime.fromisoformat(str(row["created_at"])),
            )
            self._models[mid] = model
            self._by_key[(model.component, model.name, model.revision)] = mid
        for row in data.get("stacks") or []:
            sid = UUID(str(row["stack_version_id"]))

            def _maybe_uuid(val: object) -> UUID | None:
                return UUID(str(val)) if val else None

            stack = StackVersionRecord(
                stack_version_id=sid,
                label=str(row["label"]),
                asr_mv=UUID(str(row["asr_mv"])),
                tts_mv=UUID(str(row["tts_mv"])),
                llm_mv=UUID(str(row["llm_mv"])),
                hermes_version=str(row["hermes_version"]),
                plugin_version=str(row["plugin_version"]),
                prompt_sha256=str(row["prompt_sha256"]),
                worker_config=dict(row.get("worker_config") or {}),
                git_sha=str(row["git_sha"]),
                vad_mv=_maybe_uuid(row.get("vad_mv")),
                turn_mv=_maybe_uuid(row.get("turn_mv")),
                is_production=bool(row.get("is_production")),
                created_at=datetime.fromisoformat(str(row["created_at"])),
            )
            self._stacks[sid] = stack
            self._by_label[stack.label] = sid

    def register_model(
        self,
        *,
        component: str,
        name: str,
        revision: str,
        owner: str,
        base_model: str | None = None,
        license: str | None = None,
        artifact_uri: str | None = None,
        config: dict[str, Any] | None = None,
        intended_use: str | None = None,
        out_of_scope_use: str | None = None,
        mlflow_run_id: str | None = None,
        training_data: dict[str, Any] | None = None,
        status: str = "candidate",
    ) -> ModelVersionRecord:
        if component not in COMPONENT_KINDS:
            raise RegistryError(f"unknown component {component!r}")
        if status not in MODEL_STATUSES:
            raise RegistryError(f"unknown status {status!r}")
        cfg = dict(config or {})
        key = (component, name, revision)
        with self._lock:
            if key in self._by_key:
                raise RegistryError(f"duplicate model {component}/{name}@{revision}")
            if status == "production":
                for other in self._models.values():
                    if other.component == component and other.status == "production":
                        other.status = "retired"
            mid = uuid4()
            rec = ModelVersionRecord(
                model_version_id=mid,
                component=component,
                name=name,
                revision=revision,
                owner=owner,
                status=status,
                base_model=base_model,
                license=license,
                artifact_uri=artifact_uri,
                config=cfg,
                config_sha256=config_sha256(cfg),
                training_data=training_data,
                intended_use=intended_use,
                out_of_scope_use=out_of_scope_use,
                mlflow_run_id=mlflow_run_id,
            )
            self._models[mid] = rec
            self._by_key[key] = mid
            self._persist()
            return rec

    def get_model(self, model_version_id: UUID) -> ModelVersionRecord | None:
        with self._lock:
            return self._models.get(model_version_id)

    def resolve_model_key(self, key: tuple[str, str, str]) -> UUID:
        with self._lock:
            if key not in self._by_key:
                raise RegistryError(f"unknown model key {key}")
            return self._by_key[key]

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

    def register_stack(
        self,
        *,
        label: str,
        asr_mv: UUID,
        tts_mv: UUID,
        llm_mv: UUID,
        hermes_version: str,
        plugin_version: str,
        prompt_sha256: str,
        worker_config: dict[str, Any],
        git_sha: str,
        vad_mv: UUID | None = None,
        turn_mv: UUID | None = None,
        is_production: bool = False,
    ) -> StackVersionRecord:
        with self._lock:
            if label in self._by_label:
                raise RegistryError(f"duplicate stack label {label!r}")
            for mid in (asr_mv, tts_mv, llm_mv, vad_mv, turn_mv):
                if mid is not None and mid not in self._models:
                    raise RegistryError(f"unknown model_version_id {mid}")
            if is_production:
                for other in self._stacks.values():
                    if other.is_production:
                        other.is_production = False
            sid = uuid4()
            rec = StackVersionRecord(
                stack_version_id=sid,
                label=label,
                asr_mv=asr_mv,
                tts_mv=tts_mv,
                llm_mv=llm_mv,
                vad_mv=vad_mv,
                turn_mv=turn_mv,
                hermes_version=hermes_version,
                plugin_version=plugin_version,
                prompt_sha256=prompt_sha256,
                worker_config=dict(worker_config),
                git_sha=git_sha,
                is_production=is_production,
            )
            self._stacks[sid] = rec
            self._by_label[label] = sid
            self._persist()
            return rec

    def get_stack(self, stack_version_id: UUID) -> StackVersionRecord | None:
        with self._lock:
            return self._stacks.get(stack_version_id)

    def get_stack_by_label(self, label: str) -> StackVersionRecord | None:
        with self._lock:
            sid = self._by_label.get(label)
            return self._stacks.get(sid) if sid else None

    def require_stack(self, label_or_id: str) -> StackVersionRecord:
        """Resolve stack by label or UUID; raise if missing (eval gate)."""
        try:
            sid = UUID(label_or_id)
            stack = self.get_stack(sid)
            if stack is not None:
                return stack
        except ValueError:
            pass
        stack = self.get_stack_by_label(label_or_id)
        if stack is None:
            raise RegistryError(
                f"stack {label_or_id!r} is not registered; "
                "run `callscope governance backfill` or register a stack first"
            )
        return stack

    def list_stacks(self) -> list[StackVersionRecord]:
        with self._lock:
            return list(self._stacks.values())

    def production_stack(self) -> StackVersionRecord | None:
        with self._lock:
            for s in self._stacks.values():
                if s.is_production:
                    return s
        return None


# Historic CLI labels that map onto the backfilled Mac stack (D-20260922-41).
CI_STACK_ALIASES = frozenset({"mock", "ci-mock", "local-mock", "stack-mock-v1"})


def backfill_m0_inventory(
    registry: ModelStackRegistry, *, git_sha: str = "local"
) -> StackVersionRecord:
    """Register M0/M1 chosen models + a local-mac-dev production stack (idempotent-ish)."""
    existing = registry.get_stack_by_label("local-mac-dev")
    if existing is not None:
        return existing

    def _reg(**kwargs: Any) -> ModelVersionRecord:
        try:
            return registry.register_model(**kwargs)
        except RegistryError:
            key = (kwargs["component"], kwargs["name"], kwargs["revision"])
            mid = registry.resolve_model_key(key)
            rec = registry.get_model(mid)
            if rec is None:
                raise RegistryError(f"missing model after duplicate {key}") from None
            return rec

    asr = _reg(
        component="asr",
        name="mlx-whisper-tiny",
        revision="mlx-community/whisper-tiny",
        owner="callscope",
        base_model="openai/whisper-tiny",
        license="MIT",
        intended_use="Local Mac demo ASR (Metal)",
        out_of_scope_use="Production telephony without recorded-set validation",
        status="production",
        config={"backend": "mlx_whisper"},
    )
    tts = _reg(
        component="tts",
        name="piper-en_US-lessac-medium",
        revision="v1.0",
        owner="callscope",
        license="GPL-3.0-or-later",
        intended_use="Low-latency demo TTS",
        out_of_scope_use="Redistribution of GPL voices without compliance review",
        status="production",
        config={"backend": "piper"},
    )
    llm = _reg(
        component="llm",
        name="nemotron-3.5-lightning",
        revision="nvidia/Nemotron-3_5-Lightning",
        owner="callscope",
        base_model="nvidia/Nemotron-3_5-Lightning",
        license="OpenMDW v1.1",
        intended_use="Token Factory receptionist brain via Hermes",
        out_of_scope_use="Unbudgeted live eval; medical/legal advice",
        status="production",
        config={"provider": "token_factory"},
    )
    vad = _reg(
        component="vad",
        name="silero-vad",
        revision="livekit-agents-silero-1.8.2",
        owner="callscope",
        license="MIT",
        intended_use="Worker VAD / turn onset",
        status="production",
        config={},
    )
    return registry.register_stack(
        label="local-mac-dev",
        asr_mv=asr.model_version_id,
        tts_mv=tts.model_version_id,
        llm_mv=llm.model_version_id,
        vad_mv=vad.model_version_id,
        hermes_version="0.19.0",
        plugin_version="0.0.1",
        prompt_sha256="pending-skill-hash",
        worker_config={"stack_label": "local-mac-dev"},
        git_sha=git_sha,
        is_production=True,
    )


def ensure_eval_stack(
    registry: ModelStackRegistry,
    label_or_id: str,
    *,
    git_sha: str = "local",
    auto_backfill: bool = True,
) -> StackVersionRecord:
    """Resolve a stack for eval; optionally backfill M0 and CI alias labels."""
    try:
        return registry.require_stack(label_or_id)
    except RegistryError:
        pass
    if not auto_backfill:
        raise RegistryError(
            f"stack {label_or_id!r} is not registered; "
            "run `python -m callscope.devtools.governance_cli backfill`"
        )
    base = backfill_m0_inventory(registry, git_sha=git_sha)
    try:
        return registry.require_stack(label_or_id)
    except RegistryError:
        pass
    if label_or_id in CI_STACK_ALIASES:
        existing = registry.get_stack_by_label(label_or_id)
        if existing is not None:
            return existing
        return registry.register_stack(
            label=label_or_id,
            asr_mv=base.asr_mv,
            tts_mv=base.tts_mv,
            llm_mv=base.llm_mv,
            vad_mv=base.vad_mv,
            turn_mv=base.turn_mv,
            hermes_version=base.hermes_version,
            plugin_version=base.plugin_version,
            prompt_sha256=base.prompt_sha256,
            worker_config={**base.worker_config, "alias_of": "local-mac-dev"},
            git_sha=git_sha,
            is_production=False,
        )
    raise RegistryError(
        f"stack {label_or_id!r} is not registered; "
        "run `python -m callscope.devtools.governance_cli backfill` "
        "or pass --stack local-mac-dev"
    )
