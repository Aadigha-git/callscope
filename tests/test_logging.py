import json
import logging

import pytest

from callscope.observability.logging import bind_call, configure_logging, scrub

pytestmark = pytest.mark.unit


def test_scrub_masks_phone_and_email() -> None:
    out = scrub("call me on (949) 555-0123 or 949.555.0123, mail a.b@example.com")
    assert "555" not in out
    assert "example.com" not in out
    assert out.count("[phone]") == 2
    assert "[email]" in out


def test_scrub_masks_token_factory_and_related_secrets() -> None:
    # Deliberately fake values — exercise scrub(), not real credentials.
    out = scrub(
        "TOKEN_FACTORY_API_KEY=fake-tf-key-for-scrub-test "
        "LANGSMITH_API_KEY=fake-ls-key-for-scrub-test "
        "api_key: fake-generic-key-for-scrub-test "
        "TOLOKA_API_KEY=fake-toloka-key-for-scrub-test "
        "CALLSCOPE_SERVICE_TOKEN=fake-svc-token-for-scrub-test "
        "CALLSCOPE_LIVEKIT_API_SECRET=fake-lk-secret-for-scrub-test"
    )
    assert "fake-tf-key-for-scrub-test" not in out
    assert "fake-ls-key-for-scrub-test" not in out
    assert "fake-generic-key-for-scrub-test" not in out
    assert "fake-toloka-key-for-scrub-test" not in out
    assert "fake-svc-token-for-scrub-test" not in out
    assert "fake-lk-secret-for-scrub-test" not in out
    assert out.count("[redacted]") >= 6


def test_json_lines_carry_call_id_and_scrub(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", json_output=True)
    log = logging.getLogger("t")
    with bind_call("call-1", "turn-2"):
        log.info("caller said 9495550123", extra={"stage": "asr", "note": "x@y.io"})
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["call_id"] == "call-1"
    assert line["turn_id"] == "turn-2"
    assert line["stage"] == "asr"
    assert "9495550123" not in line["msg"]
    assert line["note"] == "[email]"


def test_ids_reset_after_block(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", json_output=True)
    with bind_call("c"):
        pass
    logging.getLogger("t").info("after")
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["call_id"] is None


def test_plain_format_and_exception(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", json_output=False)
    logging.getLogger("t").info("plain")
    assert "plain" in capsys.readouterr().out
    configure_logging("INFO", json_output=True)
    try:
        raise ValueError("boom 9495550123")
    except ValueError:
        logging.getLogger("t").exception("failed")
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert "9495550123" not in line["exc"]
