"""Eval runner + persist + budget estimate/refusal (T-M3-05)."""

from __future__ import annotations

from pathlib import Path

import pytest

from callscope.eval.persist import FileEvalStore, aggregate_metrics
from callscope.eval.replay import ReplayItem, replay_item, synthetic_wav_for_text
from callscope.eval.runner import (
    EvalRunConfig,
    NoOpBizReset,
    estimate_eval_usd,
    load_golden_items,
    resolve_git_sha,
    run_eval,
    thresholds_sha256,
)
from callscope.providers.base import Msg
from callscope.providers.budget import BudgetExceededError, BudgetGuard
from callscope.providers.cassettes import (
    CassetteBrain,
    CassetteMode,
    CassetteStore,
    request_hash,
)
from callscope.providers.mock import MockBrain, MockSTT, MockTTS

pytestmark = pytest.mark.unit

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "eval_items.json"


async def _instant(_s: float) -> None:
    return None


@pytest.fixture
def golden_items() -> list[ReplayItem]:
    items = load_golden_items(GOLDEN)
    assert len(items) == 20
    return items


@pytest.mark.asyncio
async def test_text_replay_single() -> None:
    item = ReplayItem(item_id="t1", text="book Friday", scenario_id="book", intent="book")
    stt = MockSTT(transcripts=["unused"], sleep=_instant)
    brain = MockBrain(replies=["Sure, Friday works."], sleep=_instant)
    tts = MockTTS(sleep=_instant)
    result = await replay_item(item, mode="text_replay", stt=stt, brain=brain, tts=tts)
    assert result.hyp_transcript == "book Friday"
    assert result.detail["agent_text"] == "Sure, Friday works."
    assert "brain_ms" in result.latencies_ms


@pytest.mark.asyncio
async def test_stage_replay_scores_asr() -> None:
    item = ReplayItem(
        item_id="s1",
        text="hello lakeside",
        wav_bytes=synthetic_wav_for_text("hello"),
    )
    stt = MockSTT(transcripts=["hello lakeside"], sleep=_instant)
    brain = MockBrain(replies=["Hi there."], sleep=_instant)
    tts = MockTTS(sleep=_instant)
    result = await replay_item(
        item, mode="stage_replay", stt=stt, brain=brain, tts=tts, ref_asr=stt
    )
    assert result.wer == 0.0
    assert result.hyp_transcript == "hello lakeside"
    assert result.latencies_ms["stt_ms"] >= 0.0
    assert result.latencies_ms["tts_ms"] >= 0.0


@pytest.mark.asyncio
async def test_golden_20_stage_replay_with_cassettes(
    golden_items: list[ReplayItem], tmp_path: Path
) -> None:
    cassette_store = CassetteStore(tmp_path / "cassettes")
    budget = BudgetGuard(budget_usd=15.0, spend_usd=0.0, model="mock")
    model = "mock"
    # Record cassettes from MockBrain (offline).
    for item in golden_items:
        reply = f"OK. Regarding: {item.text[:40]}"
        recorder = CassetteBrain(
            MockBrain(replies=[reply], sleep=_instant),
            cassette_store,
            mode=CassetteMode.RECORD,
            budget=budget,
            model=model,
            projected_usd=0.0,
        )
        msgs = [Msg(role="user", content=item.text)]
        async for _ in recorder.stream_reply(msgs, call_id="seed", turn_id=item.item_id):
            pass
        assert cassette_store.exists(request_hash(msgs, model=model))

    dead = MockBrain(replies=["NO"], fail_at_call=1, sleep=_instant)
    brain = CassetteBrain(dead, cassette_store, mode=CassetteMode.REPLAY, model=model)
    store = FileEvalStore(tmp_path / "runs")
    biz = NoOpBizReset()

    def stt_factory(item: ReplayItem) -> MockSTT:
        return MockSTT(transcripts=[item.text], sleep=_instant)

    config = EvalRunConfig(
        dataset_id="golden-eval@v1",
        stack_version_id="stack-mock-v1",
        mode="stage_replay",
        git_sha="deadbeef",
        live=False,
        seed=7,
        concurrency=1,
        estimated_usd=0.0,
    )
    result = await run_eval(
        golden_items,
        store=store,
        stt=MockSTT(transcripts=["x"], sleep=_instant),
        brain=brain,
        tts=MockTTS(sleep=_instant),
        config=config,
        biz=biz,
        stt_factory=stt_factory,
    )
    assert result.status == "succeeded"
    assert result.n_finished == 20
    assert result.n_items == 20
    assert len(biz.calls) == 20

    run = store.load(result.run_id)
    assert run.git_sha == "deadbeef"
    assert run.dataset_id == "golden-eval@v1"
    assert run.stack_version_id == "stack-mock-v1"
    assert run.estimated_usd == 0.0
    assert run.mode == "stage_replay"
    assert len(run.item_results) == 20
    assert any(m["metric"] == "wer" and m["slice"] == "all" for m in run.metrics)
    # Perfect mock ASR → mean WER 0
    all_wer = next(m for m in run.metrics if m["metric"] == "wer" and m["slice"] == "all")
    assert all_wer["value"] == 0.0


@pytest.mark.asyncio
async def test_resume_skips_finished(tmp_path: Path) -> None:
    items = [
        ReplayItem(item_id="a", text="one"),
        ReplayItem(item_id="b", text="two"),
    ]
    store = FileEvalStore(tmp_path / "runs")
    brain = MockBrain(replies=["ok"], sleep=_instant)
    config = EvalRunConfig(
        dataset_id="d1",
        stack_version_id="s1",
        mode="text_replay",
        git_sha="abc",
    )

    def stt_factory(item: ReplayItem) -> MockSTT:
        return MockSTT(transcripts=[item.text], sleep=_instant)

    r1 = await run_eval(
        items[:1],
        store=store,
        stt=MockSTT(sleep=_instant),
        brain=brain,
        tts=MockTTS(sleep=_instant),
        config=config,
        stt_factory=stt_factory,
    )
    assert r1.n_finished == 1

    # Resume with both items — only b should be new.
    calls_before = brain._calls
    r2 = await run_eval(
        items,
        store=store,
        stt=MockSTT(sleep=_instant),
        brain=brain,
        tts=MockTTS(sleep=_instant),
        config=config,
        stt_factory=stt_factory,
        resume_run_id=r1.run_id,
    )
    assert r2.n_finished == 2
    assert brain._calls == calls_before + 1


def test_estimate_and_budget_refusal() -> None:
    projected = estimate_eval_usd(20, model="nvidia/Nemotron-3_5-Lightning")
    assert projected > 0.0
    guard = BudgetGuard(budget_usd=0.0000001, spend_usd=0.0)
    with pytest.raises(BudgetExceededError):
        guard.require_live_budget(projected)
    ok = BudgetGuard(budget_usd=15.0, spend_usd=0.0)
    ok.require_live_budget(projected)
    assert ok.estimated_usd_for_eval_run(projected) == round(projected, 8)


@pytest.mark.asyncio
async def test_live_run_persists_estimated_usd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("CALLSCOPE_ENV", "dev")
    items = [ReplayItem(item_id="x", text="hi")]
    store = FileEvalStore(tmp_path / "runs")
    projected = estimate_eval_usd(1)
    budget = BudgetGuard(budget_usd=15.0, spend_usd=0.0, model="mock")
    config = EvalRunConfig(
        dataset_id="d",
        stack_version_id="s",
        mode="text_replay",
        git_sha="g",
        live=True,
        estimated_usd=projected,
    )
    result = await run_eval(
        items,
        store=store,
        stt=MockSTT(transcripts=["hi"], sleep=_instant),
        brain=MockBrain(replies=["yo"], sleep=_instant),
        tts=MockTTS(sleep=_instant),
        config=config,
        budget=budget,
        stt_factory=lambda it: MockSTT(transcripts=[it.text], sleep=_instant),
    )
    run = store.load(result.run_id)
    assert run.estimated_usd == round(projected, 8)
    assert run.git_sha == "g"
    assert run.dataset_id == "d"
    assert run.stack_version_id == "s"


@pytest.mark.asyncio
async def test_live_refused_when_over_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("CALLSCOPE_ENV", "dev")
    items = [ReplayItem(item_id="x", text="hi")]
    store = FileEvalStore(tmp_path / "runs")
    budget = BudgetGuard(budget_usd=0.0, spend_usd=0.0)
    config = EvalRunConfig(
        dataset_id="d",
        stack_version_id="s",
        mode="text_replay",
        git_sha="g",
        live=True,
        estimated_usd=1.0,
    )
    with pytest.raises(BudgetExceededError):
        await run_eval(
            items,
            store=store,
            stt=MockSTT(sleep=_instant),
            brain=MockBrain(sleep=_instant),
            tts=MockTTS(sleep=_instant),
            config=config,
            budget=budget,
        )


def test_aggregate_metrics_empty() -> None:
    assert aggregate_metrics({}) == []


def test_thresholds_sha_and_git(tmp_path: Path) -> None:
    p = tmp_path / "t.yaml"
    p.write_text("wer: 0.1\n", encoding="utf-8")
    assert thresholds_sha256(p) is not None
    assert thresholds_sha256(None) is None
    assert resolve_git_sha(explicit="abc123") == "abc123"


def test_eval_cli_estimate(monkeypatch: pytest.MonkeyPatch) -> None:
    from callscope.devtools import eval_cli

    monkeypatch.setenv("CALLSCOPE_LLM_BUDGET_USD", "15")
    monkeypatch.setenv("CALLSCOPE_LLM_SPEND_USD", "0")
    assert eval_cli.main(["estimate", "--n-items", "20"]) == 0
    # Tiny budget → refusal on --check
    monkeypatch.setenv("CALLSCOPE_LLM_BUDGET_USD", "0.00000001")
    # Clear settings cache if any
    from callscope.config import get_settings

    get_settings.cache_clear()
    assert eval_cli.main(["estimate", "--n-items", "20", "--check"]) == 1
    get_settings.cache_clear()
