"""Governance cards, reports, risk, lifecycle tests (T-M5-04)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from callscope.governance.cards import card_is_complete, render_model_card
from callscope.governance.lifecycle import GateError, TransitionContext, check_transition
from callscope.governance.reports import render_validation_report, report_repro_fingerprint
from callscope.governance.risk import RiskRegister

pytestmark = pytest.mark.unit


def _model(**kwargs: object) -> dict[str, object]:
    base = {
        "model_version_id": str(uuid4()),
        "component": "asr",
        "name": "mlx-whisper-tiny",
        "revision": "v1",
        "owner": "callscope",
        "status": "candidate",
        "license": "MIT",
        "intended_use": "Local Mac demo ASR",
        "out_of_scope_use": "Production telephony without validation",
        "base_model": "openai/whisper-tiny",
        "config_sha256": "abc",
    }
    base.update(kwargs)
    return base


def test_card_render_and_complete(tmp_path: Path) -> None:
    model = _model()
    path = render_model_card(
        model,
        out_dir=tmp_path,
        metrics=[{"metric": "wer", "value": 0.1, "n": 10}],
    )
    assert path.is_file()
    assert card_is_complete(path)
    incomplete = render_model_card(_model(intended_use=None), out_dir=tmp_path / "b")
    assert not card_is_complete(incomplete)


def test_report_reproducible(tmp_path: Path) -> None:
    model = _model()
    a = render_validation_report(
        model=model,
        eval_run_id="run-a",
        git_sha="deadbeef",
        dataset_id="golden@v1",
        stack_version_id="local-mac-dev",
        results={"wer": 0.1},
        passed=True,
        out_dir=tmp_path,
        write_docx=True,
    )
    b = render_validation_report(
        model=model,
        eval_run_id="run-a",
        git_sha="deadbeef",
        dataset_id="golden@v1",
        stack_version_id="local-mac-dev",
        results={"wer": 0.1},
        passed=True,
        out_dir=tmp_path,
        write_docx=False,
    )
    assert report_repro_fingerprint(a) == report_repro_fingerprint(b)
    assert Path(a["report_uri"]).is_file()


def test_lifecycle_gate_matrix(tmp_path: Path) -> None:
    mid = uuid4()
    model_path = render_model_card(
        _model(model_version_id=str(mid), status="validated"),
        out_dir=tmp_path,
    )
    assert card_is_complete(model_path)
    risks = RiskRegister(root=tmp_path / "risks")
    risks.complete_assessment(mid, reviewer="bag")

    with pytest.raises(GateError) as ei:
        check_transition(
            status="candidate",
            to="validated",
            model_version_id=mid,
            ctx=TransitionContext(report_passed=False, intended_use="demo"),
        )
    assert "passing" in ei.value.unmet[0] or any("passing" in u for u in ei.value.unmet)

    check_transition(
        status="candidate",
        to="validated",
        model_version_id=mid,
        ctx=TransitionContext(
            report_id=uuid4(),
            report_passed=True,
            intended_use="demo ASR",
        ),
    )

    with pytest.raises(GateError) as e2:
        check_transition(
            status="validated",
            to="production",
            model_version_id=mid,
            ctx=TransitionContext(
                card_dir=tmp_path,
                monitoring_on=True,
                rollback_stack_id=None,
                risk_register=risks,
            ),
        )
    assert any("rollback" in u for u in e2.value.unmet)

    check_transition(
        status="validated",
        to="production",
        model_version_id=mid,
        ctx=TransitionContext(
            card_dir=tmp_path,
            monitoring_on=True,
            rollback_stack_id="local-mac-dev",
            risk_register=risks,
        ),
    )
