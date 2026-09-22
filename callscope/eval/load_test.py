"""Local concurrency / latency load harness (T-M6-01).

Runs mock caller-sim scenarios at concurrency 1 (required) and 2 (stretch),
aggregates response / barge-stop latencies, and verifies SessionCapLimiter.
Never points at a live demo window (mock transport only).
"""

from __future__ import annotations

import asyncio
import json
import resource
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from apps.api.ratelimit import SessionCapExceeded, SessionCapLimiter
from callscope.eval.runner_sim import run_one_scenario
from callscope.eval.scenarios import expand_scenario, load_all_scenarios
from callscope.eval.stats import bootstrap_percentile
from callscope.sim.caller import MockCallerTransport, SimulatedCaller

# NFR-01 hypotheses (ms) — design §12 / NFR table
NFR01_P50_MS = 1800.0
NFR01_P95_MS = 3000.0
# Hosted brain hop from S-3 (D-20260920-18) — used only for projected gap notes
HERMES_TURN_P50_MS = 2700.0
# Token Factory chat TTFT from S-6 (D-20260920-17)
TF_TTFT_P50_MS = 699.0

DEFAULT_SESSION_CAP = 2
DEFAULT_REPS = 3
DEFAULT_CONCURRENCY_LEVELS = (1, 2)


@dataclass(slots=True)
class LevelResult:
    concurrency: int
    n_calls: int
    reps: int
    response_latencies_ms: list[float] = field(default_factory=list)
    barge_stop_latencies_ms: list[float] = field(default_factory=list)
    wall_s: float = 0.0
    rss_delta_mb: float | None = None
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    barge_p50_ms: float | None = None
    barge_p95_ms: float | None = None
    meets_nfr01_mock: bool = False
    projected_p50_ms: float = 0.0
    meets_nfr01_projected: bool = False


@dataclass(slots=True)
class CapProbe:
    max_concurrent: int
    acquired: int
    third_blocked: bool
    error: str | None = None


@dataclass(slots=True)
class LoadReport:
    run_id: str
    seed: int
    session_cap: int
    levels: list[LevelResult]
    cap_probe: CapProbe
    knee_concurrency: int | None
    public_concurrency_cap: int
    notes: list[str]
    nfr01_p50_ms: float = NFR01_P50_MS
    nfr01_p95_ms: float = NFR01_P95_MS


def _rss_mb() -> float:
    # ru_maxrss is bytes on Linux, KiB on macOS
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if usage > 10_000_000:  # likely bytes
        return usage / (1024 * 1024)
    return usage / 1024


def _pct(vals: list[float], q: float) -> float:
    if not vals:
        return 0.0
    return float(bootstrap_percentile(vals, q=q, n_boot=200, seed=42).estimate)


async def _run_one_call(
    *,
    scenario_index: int,
    seed: int,
    wall_clock: bool,
) -> dict[str, Any]:
    scenarios = load_all_scenarios()
    sc = expand_scenario(scenarios[scenario_index % len(scenarios)], seed=seed, variant=0)
    transport = MockCallerTransport()
    caller = SimulatedCaller(transport=transport)
    _item_id, item = await run_one_scenario(
        sc,
        caller=caller,
        livekit_url="ws://127.0.0.1:7880",
        livekit_jwt="load-test",
        wall_clock=wall_clock,
    )
    scores = (item.detail or {}).get("sim_scores") or {}
    return {
        "response_latency_ms": float(
            scores.get("sim.response_latency_ms")
            or (item.latencies_ms or {}).get("response_latency_ms")
            or 0.0
        ),
        "barge_stop_latency_ms": scores.get("sim.barge_stop_latency_ms"),
        "sim_pass": float(scores.get("sim_pass", 0.0)),
    }


async def run_level(
    concurrency: int,
    *,
    reps: int = DEFAULT_REPS,
    seed: int = 42,
    wall_clock: bool = False,
    scenario_index: int = 0,
) -> LevelResult:
    """Run ``reps`` batches of ``concurrency`` parallel mock caller-sim calls."""
    rss0 = _rss_mb()
    t0 = time.monotonic()
    responses: list[float] = []
    barges: list[float] = []
    for rep in range(reps):
        tasks = [
            _run_one_call(
                scenario_index=scenario_index + i,
                seed=seed + rep * 100 + i,
                wall_clock=wall_clock,
            )
            for i in range(concurrency)
        ]
        results = await asyncio.gather(*tasks)
        for row in results:
            responses.append(float(row["response_latency_ms"]))
            b = row.get("barge_stop_latency_ms")
            if b is not None:
                barges.append(float(b))
    wall = time.monotonic() - t0
    rss1 = _rss_mb()
    p50 = _pct(responses, 50)
    p95 = _pct(responses, 95)
    barge_p50 = _pct(barges, 50) if barges else None
    barge_p95 = _pct(barges, 95) if barges else None
    # Mock oracle uses fixed +500 ms to first audio (runner_sim synthetic agent).
    projected = p50 + HERMES_TURN_P50_MS
    meets_mock = p50 <= NFR01_P50_MS and p95 <= NFR01_P95_MS
    meets_proj = projected <= NFR01_P50_MS and (p95 + HERMES_TURN_P50_MS) <= NFR01_P95_MS
    return LevelResult(
        concurrency=concurrency,
        n_calls=concurrency * reps,
        reps=reps,
        response_latencies_ms=responses,
        barge_stop_latencies_ms=barges,
        wall_s=wall,
        rss_delta_mb=round(rss1 - rss0, 2),
        p50_ms=p50,
        p95_ms=p95,
        barge_p50_ms=barge_p50,
        barge_p95_ms=barge_p95,
        meets_nfr01_mock=meets_mock,
        projected_p50_ms=projected,
        meets_nfr01_projected=meets_proj,
    )


def probe_session_cap(max_concurrent: int = DEFAULT_SESSION_CAP) -> CapProbe:
    limiter = SessionCapLimiter(max_concurrent=max_concurrent)
    ids = [uuid4() for _ in range(max_concurrent)]
    for cid in ids:
        limiter.try_acquire(cid)
    blocked = False
    err: str | None = None
    try:
        limiter.try_acquire(uuid4())
    except SessionCapExceeded as exc:
        blocked = True
        err = str(exc)
    for cid in ids:
        limiter.release(cid)
    return CapProbe(
        max_concurrent=max_concurrent,
        acquired=max_concurrent,
        third_blocked=blocked,
        error=err,
    )


def find_knee(levels: list[LevelResult]) -> int | None:
    """First concurrency where p95 grows >20% vs concurrency=1 (mock path)."""
    by_c = {lv.concurrency: lv for lv in levels}
    base = by_c.get(1)
    if base is None or base.p95_ms <= 0:
        return None
    for c in sorted(by_c):
        if c <= 1:
            continue
        if by_c[c].p95_ms > base.p95_ms * 1.20:
            return c
    return None


async def run_load(
    *,
    levels: tuple[int, ...] = DEFAULT_CONCURRENCY_LEVELS,
    reps: int = DEFAULT_REPS,
    seed: int = 42,
    wall_clock: bool = False,
    session_cap: int = DEFAULT_SESSION_CAP,
) -> LoadReport:
    level_results: list[LevelResult] = []
    for c in levels:
        level_results.append(await run_level(c, reps=reps, seed=seed, wall_clock=wall_clock))
    cap = probe_session_cap(session_cap)
    knee = find_knee(level_results)
    notes = [
        "Transport: MockCallerTransport + synthetic agent events (CI-safe; not live demo).",
        "Mock agent first-audio offset is fixed (~500 ms) in runner_sim; "
        "NFR-01 mock check is structural.",
        f"Projected e2e p50 adds Hermes turn p50 {HERMES_TURN_P50_MS:.0f} ms "
        f"(D-20260920-18) and cites TF TTFT p50 {TF_TTFT_P50_MS:.0f} ms "
        f"(D-20260920-17) as network floor.",
        f"SessionCapLimiter max_concurrent={session_cap}; "
        f"third acquire blocked={cap.third_blocked}.",
    ]
    if knee is None:
        notes.append(
            "No latency knee at concurrency 1→2 on the mock path "
            "(oracle latencies are schedule-based, not CPU-bound)."
        )
    else:
        notes.append(f"Mock-path knee observed at concurrency={knee}.")
    one = next((lv for lv in level_results if lv.concurrency == 1), None)
    if one is not None and not one.meets_nfr01_projected:
        notes.append(
            "NFR-01 gap: projected p50 (mock local + Hermes turn) exceeds "
            f"{NFR01_P50_MS:.0f} ms hypothesis — live Mac re-measure when demo stack is up."
        )
    return LoadReport(
        run_id=f"load-{uuid4().hex[:12]}",
        seed=seed,
        session_cap=session_cap,
        levels=level_results,
        cap_probe=cap,
        knee_concurrency=knee,
        public_concurrency_cap=session_cap,
        notes=notes,
    )


def report_to_dict(report: LoadReport) -> dict[str, Any]:
    return {
        "run_id": report.run_id,
        "seed": report.seed,
        "session_cap": report.session_cap,
        "public_concurrency_cap": report.public_concurrency_cap,
        "knee_concurrency": report.knee_concurrency,
        "nfr01_p50_ms": report.nfr01_p50_ms,
        "nfr01_p95_ms": report.nfr01_p95_ms,
        "cap_probe": asdict(report.cap_probe),
        "levels": [asdict(lv) for lv in report.levels],
        "notes": report.notes,
    }


def write_report(report: LoadReport, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / f"raw_{report.run_id}.json"
    latest = out_dir / "raw_latest.json"
    md_path = out_dir / "README.md"
    payload = report_to_dict(report)
    raw_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    latest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Local concurrency / latency load (T-M6-01)",
        "",
        f"**Run ID:** `{report.run_id}`  ",
        f"**Seed:** {report.seed}  ",
        f"**Public concurrency cap:** {report.public_concurrency_cap}  ",
        f"**Knee (mock path):** {report.knee_concurrency!r}",
        "",
        "## NFR-01 hypotheses",
        "",
        f"- p50 ≤ {report.nfr01_p50_ms:.0f} ms, p95 ≤ {report.nfr01_p95_ms:.0f} ms",
        "",
        "## Results",
        "",
        "| Concurrency | n | wall (s) | resp p50 | resp p95 | barge p50 | "
        "NFR-01 mock | projected p50 | NFR-01 projected |",
        "|---:|---:|---:|---:|---:|---:|:---:|---:|:---:|",
    ]
    for lv in report.levels:
        barge = f"{lv.barge_p50_ms:.0f}" if lv.barge_p50_ms is not None else "—"
        lines.append(
            f"| {lv.concurrency} | {lv.n_calls} | {lv.wall_s:.2f} | "
            f"{lv.p50_ms:.0f} | {lv.p95_ms:.0f} | {barge} | "
            f"{'yes' if lv.meets_nfr01_mock else 'no'} | "
            f"{lv.projected_p50_ms:.0f} | "
            f"{'yes' if lv.meets_nfr01_projected else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Chart (response p95 vs concurrency)",
            "",
            "```",
        ]
    )
    max_p95 = max((lv.p95_ms for lv in report.levels), default=1.0) or 1.0
    for lv in report.levels:
        bar_len = max(1, int(40 * lv.p95_ms / max_p95))
        lines.append(f"c={lv.concurrency} |{'█' * bar_len} {lv.p95_ms:.0f} ms")
    lines.extend(["```", "", "## Session cap probe", ""])
    cp = report.cap_probe
    lines.append(
        f"- max_concurrent={cp.max_concurrent}, acquired={cp.acquired}, "
        f"overflow_blocked={cp.third_blocked}"
    )
    if cp.error:
        lines.append(f"- error: `{cp.error}`")
    lines.extend(["", "## Notes", ""])
    for n in report.notes:
        lines.append(f"- {n}")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return {"raw": raw_path, "latest": latest, "readme": md_path}


__all__ = [
    "DEFAULT_SESSION_CAP",
    "NFR01_P50_MS",
    "NFR01_P95_MS",
    "LoadReport",
    "probe_session_cap",
    "run_load",
    "write_report",
]
