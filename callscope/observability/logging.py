"""Structured JSON logging with call/turn correlation IDs and PII scrubbing.

Rules (see .cursor/rules/30-security.mdc): never log raw transcripts, tool args, phone numbers
or emails. Everything logged passes through :func:`scrub` as a last line of defence.
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

call_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("call_id", default=None)
turn_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("turn_id", default=None)

_PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


def scrub(text: str) -> str:
    """Mask phone numbers and email addresses."""
    return _EMAIL.sub("[email]", _PHONE.sub("[phone]", text))


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": scrub(record.getMessage()),
            "call_id": call_id_var.get(),
            "turn_id": turn_id_var.get(),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            payload[key] = scrub(value) if isinstance(value, str) else value
        if record.exc_info:
            payload["exc"] = scrub(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    """Idempotently configure the root logger."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter()
        if json_output
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(level.upper())


@contextmanager
def bind_call(call_id: str, turn_id: str | None = None) -> Iterator[None]:
    """Attach call/turn IDs to every log line emitted inside the block."""
    t1 = call_id_var.set(call_id)
    t2 = turn_id_var.set(turn_id)
    try:
        yield
    finally:
        call_id_var.reset(t1)
        turn_id_var.reset(t2)
