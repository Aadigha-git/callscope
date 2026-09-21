"""Contract: CassetteBrain streaming + cancel (HermesBackend plug-in surface).

HermesBackend (T-M1-09) will be the live ``inner``; these tests lock the cassette
wrapper contract with MockBrain so CI never hits the network.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from callscope.providers.base import BrainBackend, Msg
from callscope.providers.budget import BudgetGuard
from callscope.providers.cassettes import CassetteBrain, CassetteMode, CassetteStore
from callscope.providers.mock import MockBrain

pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_cassette_brain_stream_and_cancel_contract(tmp_path: Path) -> None:
    store = CassetteStore(tmp_path / "cassettes")
    budget = BudgetGuard(budget_usd=15.0, spend_usd=0.0)
    inner: BrainBackend = MockBrain(replies=["alpha beta gamma"])
    brain: BrainBackend = CassetteBrain(
        inner, store, mode=CassetteMode.RECORD, budget=budget, model="contract"
    )
    msgs = [Msg(role="user", content="contract-prompt")]
    recorded = [d async for d in brain.stream_reply(msgs, call_id="c", turn_id="t0")]
    assert recorded[-1].kind == "done"
    assert any(d.kind == "text" for d in recorded)

    replay: BrainBackend = CassetteBrain(
        MockBrain(fail_at_call=1), store, mode=CassetteMode.REPLAY, model="contract"
    )
    got = [d async for d in replay.stream_reply(msgs, call_id="other", turn_id="t1")]
    assert [(d.kind, d.text) for d in got] == [(d.kind, d.text) for d in recorded]

    cancellable: BrainBackend = CassetteBrain(
        MockBrain(), store, mode=CassetteMode.REPLAY, model="contract"
    )
    partial: list[str] = []
    async for delta in cancellable.stream_reply(msgs, call_id="c", turn_id="t-cancel"):
        if delta.kind == "text" and delta.text:
            partial.append(delta.text)
            await cancellable.cancel("t-cancel")
    assert 1 <= len(partial) <= 2
