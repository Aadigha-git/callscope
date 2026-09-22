"""Turn-taking oracle for caller-sim eval (design §4.7 / T-M4-04)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class OracleThresholds:
    dead_air_ms: int = 2_000
    premature_overlap_ms: int = 0
    barge_stop_budget_ms: int = 500
    response_latency_budget_ms: int = 2_000


@dataclass(frozen=True, slots=True)
class OracleFinding:
    metric: str
    ok: bool
    value_ms: float | None = None
    detail: str = ""


@dataclass(slots=True)
class OracleReport:
    findings: list[OracleFinding] = field(default_factory=list)

    def metrics_dict(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for f in self.findings:
            key = f"sim.{f.metric}"
            if f.value_ms is not None:
                out[key] = float(f.value_ms)
            out[f"{key}.ok"] = 1.0 if f.ok else 0.0
        return out


def _events_of(events: list[dict[str, Any]], typ: str) -> list[dict[str, Any]]:
    return [e for e in events if e.get("type") == typ]


def score_timeline(
    events: list[dict[str, Any]],
    *,
    thresholds: OracleThresholds | None = None,
    expected_barge: bool = False,
) -> OracleReport:
    """Score premature/late endpoint, barge handling, and e2e response latency."""
    th = thresholds or OracleThresholds()
    report = OracleReport()
    sorted_ev = sorted(events, key=lambda e: int(e.get("t_ms") or 0))

    # Dead air: gap from caller stop (vad.end / stt.final) to agent first token
    caller_ends = [
        int(e["t_ms"])
        for e in sorted_ev
        if e.get("type") in {"vad.end", "stt.final", "caller.stop"}
    ]
    agent_starts = [
        int(e["t_ms"])
        for e in sorted_ev
        if e.get("type") in {"brain.first_token", "tts.first_audio", "playback.start"}
    ]
    if caller_ends and agent_starts:
        # Pair last caller end before first agent start after it
        dead = None
        for c_end in caller_ends:
            later = [a for a in agent_starts if a >= c_end]
            if later:
                dead = later[0] - c_end
                break
        if dead is not None:
            late = dead > th.dead_air_ms
            report.findings.append(
                OracleFinding(
                    metric="dead_air_ms",
                    ok=not late,
                    value_ms=float(dead),
                    detail="late_endpoint" if late else "ok",
                )
            )
            report.findings.append(
                OracleFinding(
                    metric="late_endpoint",
                    ok=not late,
                    value_ms=float(dead),
                )
            )

    # Premature endpoint: agent starts while caller still speaking
    caller_spans = [
        (int(e["t_ms"]), int(e.get("t_end_ms") or e["t_ms"]) + 200)
        for e in sorted_ev
        if e.get("type") in {"vad.start", "caller.start"}
    ]
    premature = False
    for a0 in agent_starts:
        for c0, c1 in caller_spans:
            if c0 <= a0 <= c1:
                premature = True
                break
    report.findings.append(
        OracleFinding(metric="premature_endpoint", ok=not premature, value_ms=None)
    )

    # Barge-in stop latency
    barge = _events_of(sorted_ev, "barge_in")
    playback_stop = _events_of(sorted_ev, "playback.stop")
    if expected_barge:
        if not barge:
            report.findings.append(
                OracleFinding(metric="missed_barge_in", ok=False, detail="no barge_in event")
            )
        else:
            b_t = int(barge[0]["t_ms"])
            stops = [int(e["t_ms"]) for e in playback_stop if int(e["t_ms"]) >= b_t]
            if not stops:
                report.findings.append(
                    OracleFinding(
                        metric="barge_stop_latency_ms",
                        ok=False,
                        detail="no playback.stop after barge",
                    )
                )
            else:
                lat = stops[0] - b_t
                report.findings.append(
                    OracleFinding(
                        metric="barge_stop_latency_ms",
                        ok=lat <= th.barge_stop_budget_ms,
                        value_ms=float(lat),
                    )
                )
    elif barge:
        report.findings.append(
            OracleFinding(metric="false_barge_in", ok=False, detail="unexpected barge_in")
        )
    else:
        report.findings.append(OracleFinding(metric="false_barge_in", ok=True))

    # End-to-end response latency: last caller final → first agent audio
    finals = _events_of(sorted_ev, "stt.final")
    first_audio = _events_of(sorted_ev, "tts.first_audio") or _events_of(
        sorted_ev, "playback.start"
    )
    if finals and first_audio:
        lat = int(first_audio[0]["t_ms"]) - int(finals[0]["t_ms"])
        report.findings.append(
            OracleFinding(
                metric="response_latency_ms",
                ok=lat <= th.response_latency_budget_ms,
                value_ms=float(lat),
            )
        )
    return report
