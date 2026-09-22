"""Registry + MLflow unit tests (T-M5-01)."""

from __future__ import annotations

from pathlib import Path

import pytest

from callscope.governance.mlflow_utils import default_tracking_uri, log_eval_run
from callscope.governance.registry import (
    ModelStackRegistry,
    RegistryError,
    backfill_m0_inventory,
    config_sha256,
)

pytestmark = pytest.mark.unit


def test_config_sha256_stable() -> None:
    a = config_sha256({"b": 1, "a": 2})
    b = config_sha256({"a": 2, "b": 1})
    assert a == b
    assert len(a) == 64


def test_register_model_uniqueness(tmp_path: Path) -> None:
    reg = ModelStackRegistry(root=tmp_path)
    reg.register_model(
        component="asr", name="x", revision="1", owner="bag", license="MIT", intended_use="demo"
    )
    with pytest.raises(RegistryError, match="duplicate"):
        reg.register_model(component="asr", name="x", revision="1", owner="bag")


def test_one_production_stack(tmp_path: Path) -> None:
    reg = ModelStackRegistry(root=tmp_path)
    asr = reg.register_model(component="asr", name="a", revision="1", owner="bag")
    tts = reg.register_model(component="tts", name="t", revision="1", owner="bag")
    llm = reg.register_model(component="llm", name="l", revision="1", owner="bag")
    s1 = reg.register_stack(
        label="s1",
        asr_mv=asr.model_version_id,
        tts_mv=tts.model_version_id,
        llm_mv=llm.model_version_id,
        hermes_version="0.19.0",
        plugin_version="0.0.1",
        prompt_sha256="abc",
        worker_config={},
        git_sha="deadbeef",
        is_production=True,
    )
    s2 = reg.register_stack(
        label="s2",
        asr_mv=asr.model_version_id,
        tts_mv=tts.model_version_id,
        llm_mv=llm.model_version_id,
        hermes_version="0.19.0",
        plugin_version="0.0.1",
        prompt_sha256="abc",
        worker_config={},
        git_sha="deadbeef",
        is_production=True,
    )
    assert s2.is_production is True
    assert reg.get_stack(s1.stack_version_id) is not None
    assert reg.get_stack(s1.stack_version_id).is_production is False  # type: ignore[union-attr]
    assert reg.production_stack() is not None
    assert reg.production_stack().label == "s2"  # type: ignore[union-attr]


def test_require_stack_and_backfill(tmp_path: Path) -> None:
    reg = ModelStackRegistry(root=tmp_path)
    with pytest.raises(RegistryError, match="not registered"):
        reg.require_stack("local-mac-dev")
    stack = backfill_m0_inventory(reg, git_sha="abc123")
    assert stack.label == "local-mac-dev"
    assert stack.is_production is True
    again = backfill_m0_inventory(reg, git_sha="abc123")
    assert again.stack_version_id == stack.stack_version_id
    models = reg.list_models(status="production")
    assert {m.component for m in models} >= {"asr", "tts", "llm", "vad"}
    for m in models:
        assert m.license is not None or m.component == "vad"
        assert m.intended_use or m.component == "vad"
    resolved = reg.require_stack("local-mac-dev")
    assert resolved.stack_version_id == stack.stack_version_id
    # Persist reload
    reg2 = ModelStackRegistry(root=tmp_path)
    assert reg2.require_stack(str(stack.stack_version_id)).label == "local-mac-dev"


def test_ensure_eval_stack_ci_alias(tmp_path: Path) -> None:
    from callscope.governance.registry import ensure_eval_stack

    reg = ModelStackRegistry(root=tmp_path)
    mock = ensure_eval_stack(reg, "mock", git_sha="dead")
    assert mock.label == "mock"
    assert mock.is_production is False
    prod = reg.require_stack("local-mac-dev")
    assert prod.is_production is True
    with pytest.raises(RegistryError):
        ensure_eval_stack(reg, "unknown-stack", git_sha="x", auto_backfill=False)


def test_governance_cli_backfill(tmp_path: Path) -> None:
    from callscope.devtools import governance_cli

    rc = governance_cli.main(["--registry", str(tmp_path), "backfill", "--git-sha", "abc"])
    assert rc == 0
    rc2 = governance_cli.main(["--registry", str(tmp_path), "list-models"])
    assert rc2 == 0


def test_mlflow_file_store_logs_run(tmp_path: Path) -> None:
    pytest.importorskip("mlflow")
    uri = default_tracking_uri(tmp_path / "mlruns")
    run_id = log_eval_run(
        experiment="callscope-test",
        run_name="unit",
        params={"git_sha": "abc", "dataset": "golden", "stack": "local-mac-dev"},
        metrics={"wer": 0.1, "sim_pass": 0.9},
        tags={"milestone": "M5"},
        tracking_uri=uri,
    )
    assert run_id
    assert (tmp_path / "mlruns" / "mlflow.db").is_file()
