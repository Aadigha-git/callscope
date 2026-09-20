import pytest

from callscope.config import Env, Settings

pytestmark = pytest.mark.unit


def test_defaults_are_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    # CI sets CALLSCOPE_ENV=test for the job; defaults must not depend on ambient env.
    monkeypatch.delenv("CALLSCOPE_ENV", raising=False)
    s = Settings(_env_file=None)
    assert s.env is Env.DEV
    assert not s.is_production_like


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CALLSCOPE_ENV", "demo")
    assert Settings(_env_file=None).is_production_like


def test_secrets_not_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CALLSCOPE_HERMES_API_KEY", raising=False)
    s = Settings(_env_file=None)
    assert "changeme-local-only" not in repr(s)
    assert s.hermes_api_key.get_secret_value() == "changeme-local-only"
