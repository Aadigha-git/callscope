"""LLM request/response cassettes (ADR-016 / NFR-06 / NFR-11).

CI and default runs **replay** only — never hit the network. Recording requires an
explicit live mode and a passing :class:`~callscope.providers.budget.BudgetGuard`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, cast

from callscope.observability.logging import scrub
from callscope.providers.base import BrainBackend, BrainDelta, Msg, ToolEvent
from callscope.providers.budget import BudgetGuard

CASSETTE_VERSION = 1
DEFAULT_CASSETTE_DIR = Path("eval/cassettes")

# Extra patterns beyond scrub() for fixture bodies (bearer tokens, sk- keys).
_BEARER = re.compile(r"(?i)(bearer\s+)([a-z0-9._\-]+)")
_SK = re.compile(r"\b(sk-[A-Za-z0-9]{8,})\b")


class CassetteMode(StrEnum):
    """How :class:`CassetteBrain` resolves requests."""

    REPLAY = "replay"  # load only; missing → CassetteMissingError
    RECORD = "record"  # live inner + write (requires budget)
    LIVE = "live"  # live inner; write when missing (requires budget)


class CassetteError(RuntimeError):
    """Base cassette error."""


class CassetteMissingError(CassetteError):
    """Raised when replay mode cannot find a cassette (fail closed in CI)."""

    def __init__(self, cassette_hash: str, path: Path) -> None:
        super().__init__(
            f"cassette missing for hash {cassette_hash} (expected {path}); "
            "CI/replay must not call the network — record with --live first"
        )
        self.cassette_hash = cassette_hash
        self.path = path


class CassetteLiveForbiddenError(CassetteError):
    """Raised when live/record is requested in a cassette-only environment."""


def redact_text(text: str) -> str:
    """Scrub PII/secrets for persisted cassette fixtures."""
    out = scrub(text)
    out = _BEARER.sub(r"\1[redacted]", out)
    return _SK.sub("[redacted]", out)


def _msg_payload(messages: Sequence[Msg]) -> list[dict[str, Any]]:
    return [
        {
            "role": m.role,
            "content": m.content,
            "name": m.name,
            "tool_call_id": m.tool_call_id,
        }
        for m in messages
    ]


def request_hash(
    messages: Sequence[Msg],
    *,
    model: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> str:
    """Stable content hash of the LLM request (messages + optional model/extra).

    ``call_id`` / ``turn_id`` are intentionally excluded so the same prompt
    replays across calls.
    """
    payload: dict[str, Any] = {"messages": _msg_payload(messages)}
    if model is not None:
        payload["model"] = model
    if extra:
        payload["extra"] = dict(sorted(extra.items(), key=lambda kv: kv[0]))
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def resolve_mode(*, live: bool = False, env: str | None = None) -> CassetteMode:
    """Map CLI/env to a mode. CI / ``CALLSCOPE_ENV=test`` always force replay."""
    resolved_env = (env or os.environ.get("CALLSCOPE_ENV") or "dev").lower()
    ci = os.environ.get("CI", "").lower() in {"1", "true", "yes"}
    if ci or resolved_env == "test":
        if live:
            raise CassetteLiveForbiddenError(
                "live/record LLM calls are forbidden when CI=1 or CALLSCOPE_ENV=test"
            )
        return CassetteMode.REPLAY
    flag = (os.environ.get("CALLSCOPE_LLM_MODE") or "").lower()
    if live or flag in {"live", "record"}:
        return CassetteMode.RECORD if flag == "record" else CassetteMode.LIVE
    return CassetteMode.REPLAY


@dataclass(frozen=True, slots=True)
class CassetteRecord:
    cassette_hash: str
    request: dict[str, Any]
    deltas: tuple[BrainDelta, ...]
    version: int = CASSETTE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "hash": self.cassette_hash,
            "request": self.request,
            "response": {"deltas": [_delta_to_dict(d) for d in self.deltas]},
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CassetteRecord:
        version = int(data.get("version") or CASSETTE_VERSION)
        h = str(data["hash"])
        request = dict(data.get("request") or {})
        raw_deltas = (data.get("response") or {}).get("deltas") or []
        deltas = tuple(_delta_from_dict(d) for d in raw_deltas)
        return cls(cassette_hash=h, request=request, deltas=deltas, version=version)


class CassetteStore:
    """Filesystem cassette store: ``{dir}/{hash[:2]}/{hash}.json``."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else DEFAULT_CASSETTE_DIR

    def path_for(self, cassette_hash: str) -> Path:
        return self.root / cassette_hash[:2] / f"{cassette_hash}.json"

    def exists(self, cassette_hash: str) -> bool:
        return self.path_for(cassette_hash).is_file()

    def load(self, cassette_hash: str) -> CassetteRecord:
        path = self.path_for(cassette_hash)
        if not path.is_file():
            raise CassetteMissingError(cassette_hash, path)
        data = json.loads(path.read_text(encoding="utf-8"))
        record = CassetteRecord.from_dict(data)
        if record.cassette_hash != cassette_hash:
            raise CassetteError(
                f"cassette hash mismatch: file claims {record.cassette_hash}, key {cassette_hash}"
            )
        return record

    def save(self, record: CassetteRecord) -> Path:
        path = self.path_for(record.cassette_hash)
        path.parent.mkdir(parents=True, exist_ok=True)
        redacted = _redact_record(record)
        path.write_text(
            json.dumps(redacted.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path


class CassetteBrain:
    """``BrainBackend`` wrapper: replay cassettes or record live inner replies."""

    def __init__(
        self,
        inner: BrainBackend,
        store: CassetteStore,
        *,
        mode: CassetteMode = CassetteMode.REPLAY,
        budget: BudgetGuard | None = None,
        model: str | None = None,
        projected_usd: float = 0.01,
    ) -> None:
        self._inner = inner
        self._store = store
        self._mode = mode
        self._budget = budget
        self._model = model
        self._projected_usd = projected_usd
        self._cancelled: set[str] = set()

    @property
    def mode(self) -> CassetteMode:
        return self._mode

    async def cancel(self, turn_id: str) -> None:
        self._cancelled.add(turn_id)
        await self._inner.cancel(turn_id)

    async def stream_reply(
        self,
        messages: list[Msg],
        *,
        call_id: str,
        turn_id: str,
    ) -> AsyncIterator[BrainDelta]:
        h = request_hash(messages, model=self._model)
        if self._mode is CassetteMode.REPLAY:
            record = self._store.load(h)
            async for delta in self._replay(record, turn_id=turn_id):
                yield delta
            return

        if self._store.exists(h) and self._mode is CassetteMode.LIVE:
            record = self._store.load(h)
            async for delta in self._replay(record, turn_id=turn_id):
                yield delta
            return

        if self._budget is None:
            raise CassetteError("live/record requires a BudgetGuard")
        self._budget.require_live_budget(self._projected_usd)

        captured: list[BrainDelta] = []
        async for delta in self._inner.stream_reply(messages, call_id=call_id, turn_id=turn_id):
            if turn_id in self._cancelled:
                break
            captured.append(delta)
            yield delta

        request = {
            "messages": _msg_payload(messages),
            "model": self._model,
            "call_id": call_id,
            "turn_id": turn_id,
        }
        self._store.save(CassetteRecord(cassette_hash=h, request=request, deltas=tuple(captured)))

    async def _replay(self, record: CassetteRecord, *, turn_id: str) -> AsyncIterator[BrainDelta]:
        for delta in record.deltas:
            if turn_id in self._cancelled:
                return
            yield delta


def _delta_to_dict(delta: BrainDelta) -> dict[str, Any]:
    out: dict[str, Any] = {"kind": delta.kind}
    if delta.text is not None:
        out["text"] = delta.text
    if delta.tool_event is not None:
        te = delta.tool_event
        out["tool_event"] = {
            "name": te.name,
            "arguments": te.arguments,
            "tool_call_id": te.tool_call_id,
        }
    return out


def _delta_from_dict(data: Mapping[str, Any]) -> BrainDelta:
    kind_raw = str(data["kind"])
    if kind_raw not in {"text", "tool_event", "done"}:
        raise CassetteError(f"unknown delta kind: {kind_raw!r}")
    kind = cast(Literal["text", "tool_event", "done"], kind_raw)
    tool_event = None
    raw_te = data.get("tool_event")
    if raw_te is not None:
        tool_event = ToolEvent(
            name=str(raw_te["name"]),
            arguments=dict(raw_te.get("arguments") or {}),
            tool_call_id=raw_te.get("tool_call_id"),
        )
    return BrainDelta(kind=kind, text=data.get("text"), tool_event=tool_event)


def _redact_record(record: CassetteRecord) -> CassetteRecord:
    req = cast(dict[str, Any], _redact_value(record.request))
    deltas: list[BrainDelta] = []
    for d in record.deltas:
        text = redact_text(d.text) if d.text is not None else None
        te = d.tool_event
        if te is not None:
            args = cast(dict[str, Any], _redact_value(te.arguments))
            te = ToolEvent(name=te.name, arguments=args, tool_call_id=te.tool_call_id)
        deltas.append(BrainDelta(kind=d.kind, text=text, tool_event=te))
    return CassetteRecord(
        cassette_hash=record.cassette_hash,
        request=req,
        deltas=tuple(deltas),
        version=record.version,
    )


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [_redact_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _redact_value(v) for k, v in value.items()}
    return value
