"""Synthetic review-demo call specs (planted failures for labelling practice)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SeedCallSpec:
    channel: str
    flagged: bool
    flag_reasons: tuple[str, ...]
    root_causes: tuple[str, ...]
    planted_rc: str | None
    severity: int
    transcript_caller: str
    transcript_agent: str
    condition: str


# Rotating planted failure patterns (40 unique-enough calls).
_PATTERNS: tuple[SeedCallSpec, ...] = (
    SeedCallSpec(
        "browser",
        True,
        ("low_asr_confidence",),
        ("RC-ASR-ENT",),
        "RC-ASR-ENT",
        3,
        "book me for tuesday at three",
        "I can book Tuesday at 3pm.",
        "C0",
    ),
    SeedCallSpec(
        "browser",
        True,
        ("tool_arg_not_in_asr",),
        ("RC-TOOL-ARGS",),
        "RC-TOOL-ARGS",
        3,
        "schedule something soon",
        "Booking 555-0199 for Friday.",
        "C1",
    ),
    SeedCallSpec(
        "browser",
        True,
        ("caller_repetition",),
        ("RC-ASR-DROP",),
        "RC-ASR-DROP",
        2,
        "what? sorry, I said Tuesday",
        "Could you repeat that?",
        "C2",
    ),
    SeedCallSpec(
        "sim",
        True,
        ("dead_air",),
        ("RC-TURN-LATE",),
        "RC-TURN-LATE",
        2,
        "hello?",
        "...",
        "C0",
    ),
    SeedCallSpec(
        "browser",
        True,
        ("agent_while_caller",),
        ("RC-TURN-EARLY",),
        "RC-TURN-EARLY",
        3,
        "I need HVAC repair",
        "Sure, booking now.",
        "C3",
    ),
    SeedCallSpec(
        "browser",
        True,
        ("barge_restart",),
        ("RC-TURN-BARGE-MISS",),
        "RC-TURN-BARGE-MISS",
        3,
        "wait no Friday",
        "As I was saying about Tuesday…",
        "C1",
    ),
    SeedCallSpec(
        "browser",
        True,
        ("policy_denial",),
        ("RC-LLM-POLICY",),
        "RC-LLM-POLICY",
        4,
        "cancel without confirming",
        "I cannot cancel without confirmation.",
        "C0",
    ),
    SeedCallSpec(
        "browser",
        True,
        ("tool_error",),
        ("RC-TOOL-ERR",),
        "RC-TOOL-ERR",
        3,
        "book Friday morning",
        "Sorry, the booking service failed.",
        "C4",
    ),
    SeedCallSpec(
        "browser",
        True,
        ("unsupported_claim",),
        ("RC-LLM-HALLU",),
        "RC-LLM-HALLU",
        4,
        "do you do free water heaters?",
        "Yes we always install free water heaters.",
        "C0",
    ),
    SeedCallSpec(
        "browser",
        True,
        ("early_hangup",),
        ("RC-SYS-OTHER",),
        "RC-SYS-OTHER",
        2,
        "never mind",
        "Hello, Lakeside Home Services.",
        "C5",
    ),
)


def build_seed_specs(n: int = 40) -> list[SeedCallSpec]:
    """Return ``n`` planted call specs (cycles patterns; some clean)."""
    if n < 1:
        raise ValueError("n must be >= 1")
    out: list[SeedCallSpec] = []
    for i in range(n):
        if i % 5 == 4:
            out.append(
                SeedCallSpec(
                    channel="browser",
                    flagged=False,
                    flag_reasons=(),
                    root_causes=(),
                    planted_rc=None,
                    severity=1,
                    transcript_caller="thanks, that works",
                    transcript_agent="You're booked for Thursday at 10am.",
                    condition="C0",
                )
            )
        else:
            out.append(_PATTERNS[i % len(_PATTERNS)])
    return out


def root_cause_distribution(labels: list[dict[str, Any]]) -> dict[str, int]:
    """Count labels by root_cause_code."""
    counts: dict[str, int] = {}
    for lab in labels:
        code = str(lab.get("root_cause_code") or "")
        if not code:
            continue
        counts[code] = counts.get(code, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def attribution_agreement(
    human: list[str],
    auto: list[str],
) -> dict[str, float]:
    """Simple set-overlap agreement between human and auto RC codes."""
    h, a = set(human), set(auto)
    if not h and not a:
        return {"precision": 1.0, "recall": 1.0, "jaccard": 1.0}
    inter = len(h & a)
    prec = inter / len(a) if a else 0.0
    rec = inter / len(h) if h else 0.0
    jac = inter / len(h | a) if (h | a) else 0.0
    return {"precision": prec, "recall": rec, "jaccard": jac}
