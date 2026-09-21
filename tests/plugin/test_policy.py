"""Table-driven policy tests (T-M2-03)."""

from __future__ import annotations

from pathlib import Path

import pytest
from hermes_callscope.policy import (
    PER_CALL_BUDGET,
    Allow,
    Deny,
    PolicyState,
    evaluate,
    record_success,
)


@pytest.fixture
def state() -> PolicyState:
    s = PolicyState()
    s.register_call("call-1")
    return s


def test_allow_lookup(state: PolicyState) -> None:
    d = evaluate("lookup_faq", {"call_id": "call-1", "query": "hours"}, state)
    assert isinstance(d, Allow)


def test_deny_missing_confirmation(state: PolicyState) -> None:
    d = evaluate(
        "book_appointment",
        {
            "call_id": "call-1",
            "phone": "2065550100",
            "confirmed": False,
            "customer_name": "A",
            "service_type": "hvac_repair",
            "slot_id": "S",
            "address": "1 Main 98101",
        },
        state,
    )
    assert isinstance(d, Deny)
    assert d.rule == "missing_confirmation"


def test_deny_inactive_call(state: PolicyState) -> None:
    d = evaluate("lookup_faq", {"call_id": "other", "query": "x"}, state)
    assert isinstance(d, Deny)
    assert d.rule == "inactive_call"


def test_deny_bad_phone(state: PolicyState) -> None:
    d = evaluate(
        "book_appointment",
        {
            "call_id": "call-1",
            "phone": "123",
            "confirmed": True,
            "customer_name": "A",
            "service_type": "hvac_repair",
            "slot_id": "S",
            "address": "1 Main",
        },
        state,
    )
    assert isinstance(d, Deny)
    assert d.rule == "invalid_phone"


def test_budget_12_vs_13(state: PolicyState) -> None:
    tools = [
        "lookup_faq",
        "check_availability",
        "transfer_to_human",
        "request_callback",
    ]
    for i in range(PER_CALL_BUDGET):
        name = tools[i % len(tools)]
        args: dict = {"call_id": "call-1", "confirmed": True}
        if name == "lookup_faq":
            args["query"] = f"q{i}"
        elif name == "check_availability":
            args.update(
                {
                    "service_type": "hvac_repair",
                    "date_from": "2099-01-01",
                    "date_to": "2099-01-07",
                    "zip": "98101",
                }
            )
        elif name == "transfer_to_human":
            args["reason"] = "test"
        else:
            args.update(
                {
                    "customer_name": "A",
                    "phone": "2065550100",
                    "reason": "test",
                }
            )
        d = evaluate(name, args, state)
        assert isinstance(d, Allow), d
        record_success(name, "call-1", state)
    d = evaluate("lookup_faq", {"call_id": "call-1", "query": "overflow"}, state)
    assert isinstance(d, Deny)
    assert d.rule == "tool_budget"


def test_invalid_confirmation_code(state: PolicyState) -> None:
    d = evaluate(
        "cancel_appointment",
        {
            "call_id": "call-1",
            "confirmation_code": "BAD",
            "phone_last4": "0100",
            "confirmed": True,
        },
        state,
    )
    assert isinstance(d, Deny)
    assert d.rule == "invalid_confirmation_code"


def test_selftest_denies_extra_toolset(tmp_path: Path) -> None:
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[2]
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "platform_toolsets:\n  api_server:\n    - callscope-receptionist\n    - terminal\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(root / "infra/hermes/toolset_selftest.py"),
            "--config",
            str(bad),
            "--allowlist",
            str(root / "infra/hermes/toolset_allowlist.txt"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "FAIL" in proc.stderr
