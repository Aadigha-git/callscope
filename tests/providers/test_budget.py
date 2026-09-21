"""Unit tests for LLM budget guard (T-M1-12)."""

from __future__ import annotations

import pytest

from callscope.config import Settings
from callscope.devtools.budget_cli import main
from callscope.providers.budget import (
    DEFAULT_MODEL,
    BudgetExceededError,
    BudgetGuard,
    cost_from_usage,
    estimate_usd,
    format_status,
    price_for,
)

pytestmark = pytest.mark.unit


def test_estimate_usd_matches_catalog_math() -> None:
    # Lightning: $0.06 / $0.24 per 1M → 4000 in + 300 out = 0.00024 + 0.000072 = 0.000312
    assert estimate_usd(4000, 300, model="nvidia/Nemotron-3_5-Lightning") == pytest.approx(0.000312)


def test_cost_from_usage_openai_shape() -> None:
    usage = {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500}
    assert cost_from_usage(usage, model=DEFAULT_MODEL) == pytest.approx(
        estimate_usd(1000, 500, model=DEFAULT_MODEL)
    )


def test_unknown_model_raises() -> None:
    with pytest.raises(KeyError, match="unknown"):
        price_for("not-a-real/model")


def test_check_live_allows_within_budget() -> None:
    guard = BudgetGuard(budget_usd=15.0, spend_usd=14.9, model=DEFAULT_MODEL)
    guard.check_live(0.05)
    assert not guard.would_exceed(0.05)


def test_check_live_refuses_over_budget() -> None:
    guard = BudgetGuard(budget_usd=15.0, spend_usd=14.99, model=DEFAULT_MODEL)
    with pytest.raises(BudgetExceededError) as ei:
        guard.require_live_budget(0.02)
    assert ei.value.projected_usd == 0.02
    assert ei.value.status.remaining_usd == pytest.approx(0.01)


def test_record_spend_accumulates() -> None:
    guard = BudgetGuard(budget_usd=15.0, spend_usd=1.0)
    assert guard.record_spend(0.25) == pytest.approx(1.25)
    assert guard.status().spend_usd == pytest.approx(1.25)


def test_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CALLSCOPE_LLM_BUDGET_USD", "10")
    monkeypatch.setenv("CALLSCOPE_LLM_SPEND_USD", "2.5")
    monkeypatch.setenv("TOKEN_FACTORY_MODEL", "nvidia/Nemotron-3_5-Lightning")
    from callscope.config import get_settings

    get_settings.cache_clear()
    guard = BudgetGuard.from_settings(Settings(_env_file=None))
    assert guard.budget_usd == 10.0
    assert guard.spend_usd == 2.5
    assert guard.model == "nvidia/Nemotron-3_5-Lightning"
    get_settings.cache_clear()


def test_cli_estimate_no_network(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CALLSCOPE_LLM_BUDGET_USD", "15")
    monkeypatch.setenv("CALLSCOPE_LLM_SPEND_USD", "0")
    from callscope.config import get_settings

    get_settings.cache_clear()
    code = main(
        [
            "--estimate",
            "--prompt-tokens",
            "4000",
            "--completion-tokens",
            "300",
            "--model",
            "nvidia/Nemotron-3_5-Lightning",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "Estimate:" in out
    assert "0.000312" in out
    get_settings.cache_clear()


def test_cli_check_refuses(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CALLSCOPE_LLM_BUDGET_USD", "0.0001")
    monkeypatch.setenv("CALLSCOPE_LLM_SPEND_USD", "0")
    from callscope.config import get_settings

    get_settings.cache_clear()
    code = main(
        [
            "--check",
            "--estimate",
            "--prompt-tokens",
            "4000",
            "--completion-tokens",
            "300",
            "--model",
            "nvidia/Nemotron-3_5-Lightning",
        ]
    )
    assert code == 1
    err = capsys.readouterr().err
    assert "REFUSED" in err
    get_settings.cache_clear()


def test_format_status_readable() -> None:
    guard = BudgetGuard(budget_usd=15.0, spend_usd=1.5)
    text = format_status(guard.status())
    assert "$1.500000 spent" in text
    assert "$15.00 cap" in text


def test_estimated_usd_for_eval_run() -> None:
    guard = BudgetGuard()
    assert guard.estimated_usd_for_eval_run(0.00123456789) == 0.00123457
