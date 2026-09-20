"""Prometheus metrics catalogue (names follow the design doc, section 4.10)."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, start_http_server

LATENCY_BUCKETS = (0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 6.0, 10.0)

RESPONSE_LATENCY = Histogram(
    "callscope_response_latency_seconds",
    "End of caller speech to first agent audio",
    buckets=LATENCY_BUCKETS,
)
STAGE_LATENCY = Histogram(
    "callscope_stage_latency_seconds",
    "Per-stage latency (endpoint, asr_final, brain_ttft, first_sentence, tts_ttfb)",
    ["stage"],
    buckets=LATENCY_BUCKETS,
)
BARGE_IN_STOP = Histogram(
    "callscope_barge_in_stop_seconds",
    "VAD onset to agent audio stopped (worker side)",
    buckets=(0.05, 0.1, 0.15, 0.2, 0.25, 0.35, 0.5, 1.0),
)
ACTIVE_CALLS = Gauge("callscope_active_calls", "Calls currently in progress")
CALLS_TOTAL = Counter("callscope_calls_total", "Completed calls", ["end_reason"])
ASR_CONFIDENCE = Histogram(
    "callscope_asr_confidence",
    "Turn-level ASR average confidence (drift proxy)",
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0),
)
TOOL_CALLS = Counter("callscope_tool_calls_total", "Tool invocations", ["name", "status"])
POLICY_DENIED = Counter("callscope_policy_denied_total", "Policy hook denials", ["rule"])
PROVIDER_ERRORS = Counter(
    "callscope_provider_errors_total", "Provider failures by stage", ["stage"]
)


def observe_stage(stage: str, seconds: float) -> None:
    STAGE_LATENCY.labels(stage=stage).observe(seconds)


def start_metrics_server(port: int) -> None:  # pragma: no cover - thin wrapper
    start_http_server(port)
