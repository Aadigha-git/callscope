"""Cassette store unit + contract tests (no network)."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from callscope.providers.base import BrainDelta, Msg
from callscope.providers.budget import BudgetExceededError, BudgetGuard
from callscope.providers.cassettes import (
    CassetteBrain,
    CassetteLiveForbiddenError,
    CassetteMissingError,
    CassetteMode,
    CassetteRecord,
    CassetteStore,
    redact_text,
    request_hash,
    resolve_mode,
)
from callscope.providers.mock import MockBrain

pytestmark = pytest.mark.unit

AsyncSleep = Callable[[float], Awaitable[None]]


@pytest.fixture
def instant_sleep() -> AsyncSleep:
    async def _sleep(_seconds: float) -> None:
        return None

    return _sleep


@pytest.fixture
def store(tmp_path: Path) -> CassetteStore:
    return CassetteStore(tmp_path / "cassettes")


def test_request_hash_stable_ignores_call_ids() -> None:
    msgs = [Msg(role="user", content="book Friday")]
    h1 = request_hash(msgs, model="m1")
    h2 = request_hash(msgs, model="m1")
    assert h1 == h2
    assert request_hash(msgs, model="m2") != h1


def test_redact_secrets() -> None:
    # Concatenate so gitleaks does not flag fixture strings (see tests/test_logging.py allowlist).
    tf = "TOKEN_FACTORY_API_KEY" + "=" + "fake-tf-key-for-scrub-test"
    assert "[redacted]" in redact_text(tf)
    assert "[redacted]" in redact_text("Authorization: Bearer tok_xyz")
    assert "[redacted]" in redact_text("use sk-abcdefghijklmnop please")


@pytest.mark.asyncio
async def test_record_then_identical_replay(
    store: CassetteStore, instant_sleep: AsyncSleep
) -> None:
    inner = MockBrain(replies=["hello lakeside"], sleep=instant_sleep)
    budget = BudgetGuard(budget_usd=15.0, spend_usd=0.0)
    recorder = CassetteBrain(inner, store, mode=CassetteMode.RECORD, budget=budget, model="mock")
    msgs = [Msg(role="user", content="hi")]
    live = [d async for d in recorder.stream_reply(msgs, call_id="c1", turn_id="t1")]
    assert live[-1].kind == "done"
    h = request_hash(msgs, model="mock")
    assert store.exists(h)

    # Replay must not touch inner (fail_at_call would fire on 2nd call).
    dead = MockBrain(replies=["SHOULD NOT RUN"], fail_at_call=1, sleep=instant_sleep)
    player = CassetteBrain(dead, store, mode=CassetteMode.REPLAY, model="mock")
    replayed = [d async for d in player.stream_reply(msgs, call_id="c9", turn_id="t9")]
    assert [(d.kind, d.text) for d in replayed] == [(d.kind, d.text) for d in live]


@pytest.mark.asyncio
async def test_replay_missing_fails_closed(store: CassetteStore) -> None:
    brain = CassetteBrain(MockBrain(), store, mode=CassetteMode.REPLAY, model="m")
    with pytest.raises(CassetteMissingError):
        async for _ in brain.stream_reply(
            [Msg(role="user", content="missing")], call_id="c", turn_id="t"
        ):
            pass


@pytest.mark.asyncio
async def test_live_refused_when_budget_exceeded(store: CassetteStore) -> None:
    inner = MockBrain(replies=["x"])
    budget = BudgetGuard(budget_usd=1.0, spend_usd=1.0)
    brain = CassetteBrain(
        inner,
        store,
        mode=CassetteMode.RECORD,
        budget=budget,
        projected_usd=0.5,
        model="m",
    )
    with pytest.raises(BudgetExceededError):
        async for _ in brain.stream_reply(
            [Msg(role="user", content="pay")], call_id="c", turn_id="t"
        ):
            pass
    assert list(store.root.rglob("*.json")) == []


@pytest.mark.asyncio
async def test_replay_cancel_stops_stream(store: CassetteStore) -> None:
    inner = MockBrain(replies=["one two three four five"])
    budget = BudgetGuard(budget_usd=15.0, spend_usd=0.0)
    recorder = CassetteBrain(inner, store, mode=CassetteMode.RECORD, budget=budget, model="m")
    msgs = [Msg(role="user", content="long")]
    async for _ in recorder.stream_reply(msgs, call_id="c", turn_id="t-rec"):
        pass

    player = CassetteBrain(MockBrain(), store, mode=CassetteMode.REPLAY, model="m")
    out: list[str] = []
    kinds: list[str] = []
    async for delta in player.stream_reply(msgs, call_id="c", turn_id="t-cancel"):
        kinds.append(delta.kind)
        if delta.kind == "text" and delta.text:
            out.append(delta.text)
            await player.cancel("t-cancel")
    assert 1 <= len(out) <= 2
    assert "done" not in kinds

    full = [
        d
        async for d in CassetteBrain(
            MockBrain(), store, mode=CassetteMode.REPLAY, model="m"
        ).stream_reply(msgs, call_id="c", turn_id="t-full")
    ]
    assert full[-1].kind == "done"


def test_resolve_mode_ci_forces_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("CALLSCOPE_ENV", "dev")
    assert resolve_mode(live=False) is CassetteMode.REPLAY
    with pytest.raises(CassetteLiveForbiddenError):
        resolve_mode(live=True)


def test_resolve_mode_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CI", raising=False)
    assert resolve_mode(live=False, env="test") is CassetteMode.REPLAY
    with pytest.raises(CassetteLiveForbiddenError):
        resolve_mode(live=True, env="test")


def test_resolve_mode_live_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("CALLSCOPE_ENV", "dev")
    assert resolve_mode(live=True) is CassetteMode.LIVE


@pytest.mark.asyncio
async def test_live_mode_replays_when_cassette_exists(store: CassetteStore) -> None:
    msgs = [Msg(role="user", content="cached")]
    budget = BudgetGuard(budget_usd=15.0, spend_usd=0.0)
    r1 = CassetteBrain(
        MockBrain(replies=["from-record"]),
        store,
        mode=CassetteMode.RECORD,
        budget=budget,
        model="m",
    )
    first = [d async for d in r1.stream_reply(msgs, call_id="c", turn_id="t1")]
    r2 = CassetteBrain(
        MockBrain(replies=["nope"], fail_at_call=1),
        store,
        mode=CassetteMode.LIVE,
        budget=budget,
        model="m",
    )
    second = [d async for d in r2.stream_reply(msgs, call_id="c", turn_id="t2")]
    assert [(d.kind, d.text) for d in second] == [(d.kind, d.text) for d in first]


def test_saved_cassette_is_redacted(store: CassetteStore) -> None:
    secret = "TOKEN_FACTORY_API_KEY" + "=" + "fake-tf-key-for-scrub-test"
    record = CassetteRecord(
        cassette_hash="ab" + "c" * 62,
        request={"messages": [{"role": "user", "content": secret}]},
        deltas=(BrainDelta(kind="text", text="Bearer tok_abc"), BrainDelta(kind="done")),
    )
    path = store.save(record)
    blob = json.dumps(json.loads(path.read_text(encoding="utf-8")))
    assert "fake-tf-key-for-scrub-test" not in blob
    assert "tok_abc" not in blob
    assert "[redacted]" in blob
