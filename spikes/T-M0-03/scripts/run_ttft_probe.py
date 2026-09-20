#!/usr/bin/env python3
"""T-M0-03: Hermes per-turn TTFT overhead vs Token Factory direct (S-2).

50 scripted turns on the chosen model (D-20260920-18):
  (a) OpenAI client → Token Factory (stream)
  (b) Hermes API server → Token Factory custom provider (stream)

Records TTFT p50/p95, prompt/completion tokens, estimated USD.
Never prints the API key. Cap spend with --max-usd (default 1.0).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import statistics
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
HERMES_HOME = ROOT / "hermes_home"
# Prefer sibling spike venv with hermes already installed.
VENV_CANDIDATES = [
    ROOT / ".venv",
    ROOT.parents[0] / "T-M0-04" / ".venv",
    ROOT.parents[0] / "T-M0-02" / ".venv",
]

API_KEY = "spike-api-key-not-a-secret"
HERMES_PORT = 18644
MODEL = "nvidia/Nemotron-3_5-Lightning"
PRICE_IN = 0.06
PRICE_OUT = 0.24

SLIM_SYSTEM = (
    "You are the phone receptionist for fictional Lakeside Home Services. "
    "Reply in one short spoken sentence. Do not call tools."
)

# 50 short turns (FAQ / ack) — no tool pressure so TTFT is comparable.
TURNS: list[str] = [
    "What are your hours?",
    "Are you open Saturday?",
    "What is your service area?",
    "How much is a standard visit?",
    "Do you do HVAC tune-ups?",
    "Is downtown Lakeside covered?",
    "What time do you close on weekdays?",
    "Can I get a rough price range?",
    "Do you serve Lakeside County?",
    "Thanks, that helps.",
    "How far do you travel?",
    "Is Sunday available for booking info?",
    "What services do you offer?",
    "Do you handle plumbing?",
    "Do you handle electrical?",
    "Do you handle appliances?",
    "Is there a weekend surcharge?",
    "Can I leave a callback request later?",
    "Who is the company again?",
    "Please keep answers brief.",
    "What are morning hours?",
    "What are afternoon hours?",
    "Do you take same-day requests?",
    "Is Maple Street in range?",
    "Is Oak Avenue in range?",
    "Confirm you are a fictional demo.",
    "Say hello briefly.",
    "Repeat the company name.",
    "Give one sentence about hours.",
    "Give one sentence about area.",
    "Give one sentence about pricing.",
    "Acknowledge without tools.",
    "Say you can take a callback.",
    "Say you can book later.",
    "Ask me to confirm details later.",
    "Offer a human handoff option.",
    "Keep this under ten words.",
    "Reply with a greeting only.",
    "Confirm you understood briefly.",
    "State opening time only.",
    "State closing time only.",
    "State the starting visit price.",
    "State HVAC tune-up price.",
    "Say yes you cover the county.",
    "Say no personal data is stored.",
    "Remind me this is fictional.",
    "Thank the caller briefly.",
    "Invite the next question.",
    "Say standby while checking FAQ.",
    "End with a short goodbye option.",
]


@dataclass
class TurnSample:
    path: str
    turn_idx: int
    ttft_ms: float
    total_ms: float
    prompt_tokens: int
    completion_tokens: int
    estimated_usd: float
    ok: bool
    error: str | None = None
    preview: str = ""


def _pct(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def load_tf_key() -> str:
    key = os.environ.get("TOKEN_FACTORY_API_KEY") or os.environ.get("NEBIUS_API_KEY") or ""
    if key.strip():
        return key.strip()
    env_path = ROOT.parents[1] / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("TOKEN_FACTORY_API_KEY=") or line.startswith("NEBIUS_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def find_venv() -> Path:
    for p in VENV_CANDIDATES:
        if (p / "bin" / "hermes").is_file():
            return p
    raise SystemExit("No hermes venv found; create spikes/T-M0-03/.venv with hermes-agent==0.19.0")


def setup_hermes(tf_key: str, base_url: str, venv: Path) -> None:
    if HERMES_HOME.exists():
        shutil.rmtree(HERMES_HOME)
    HERMES_HOME.mkdir(parents=True)
    # No plugin tools — measure pure chat TTFT through Hermes.
    config = {
        "model": {
            "provider": "custom",
            "model": MODEL,
            "base_url": base_url.rstrip("/"),
            "api_key": tf_key,
        },
        "agent": {"max_turns": 2},
        "platform_toolsets": {"api_server": []},
        "plugins": {"enabled": [], "disabled": []},
        # Slim profile (design S-2 / R-02): no persistent memory injection.
        "memory": {"memory_enabled": False},
        "skills": {"external_dirs": []},
    }
    (HERMES_HOME / "config.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )
    (HERMES_HOME / ".env").write_text(
        "\n".join(
            [
                "API_SERVER_ENABLED=true",
                f"API_SERVER_KEY={API_KEY}",
                "API_SERVER_HOST=127.0.0.1",
                f"API_SERVER_PORT={HERMES_PORT}",
                f"OPENAI_API_KEY={tf_key}",
                f"OPENAI_BASE_URL={base_url.rstrip('/')}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def wait_http(url: str, timeout: float = 120.0) -> None:
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code < 500:
                return
            last = f"status={r.status_code}"
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
        time.sleep(0.4)
    raise RuntimeError(f"timeout waiting for {url}: {last}")


def stream_ttft(
    *,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout: float = 120.0,
) -> TurnSample:
    """POST streaming chat; TTFT = monotonic time to first non-empty content delta."""
    t0 = time.perf_counter()
    ttft: float | None = None
    text_parts: list[str] = []
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    err: str | None = None
    try:
        with httpx.Client(timeout=timeout) as client:
            with client.stream("POST", url, headers=headers, json=body) as resp:
                if resp.status_code >= 400:
                    err = f"http_{resp.status_code}:{resp.read().decode('utf-8', errors='replace')[:200]}"
                else:
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        if line.startswith(":"):
                            continue
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            chunk = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(chunk.get("usage"), dict):
                            usage["prompt_tokens"] = int(
                                chunk["usage"].get("prompt_tokens") or usage["prompt_tokens"]
                            )
                            usage["completion_tokens"] = int(
                                chunk["usage"].get("completion_tokens")
                                or usage["completion_tokens"]
                            )
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        content = delta.get("content")
                        if content:
                            if ttft is None:
                                ttft = (time.perf_counter() - t0) * 1000.0
                            text_parts.append(str(content))
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
    total_ms = (time.perf_counter() - t0) * 1000.0
    if ttft is None and not err:
        err = "no_content_delta"
        ttft = total_ms
    pt, ct = usage["prompt_tokens"], usage["completion_tokens"]
    usd = (pt * PRICE_IN + ct * PRICE_OUT) / 1_000_000.0
    return TurnSample(
        path="",
        turn_idx=-1,
        ttft_ms=round(ttft or total_ms, 2),
        total_ms=round(total_ms, 2),
        prompt_tokens=pt,
        completion_tokens=ct,
        estimated_usd=round(usd, 8),
        ok=err is None,
        error=err,
        preview="".join(text_parts)[:120],
    )


def summarize(path: str, samples: list[TurnSample]) -> dict[str, Any]:
    ok = [s for s in samples if s.ok]
    ttfts = sorted(s.ttft_ms for s in ok)
    return {
        "path": path,
        "n": len(samples),
        "n_ok": len(ok),
        "ttft_p50_ms": round(_pct(ttfts, 50), 2) if ttfts else None,
        "ttft_p95_ms": round(_pct(ttfts, 95), 2) if ttfts else None,
        "ttft_mean_ms": round(statistics.fmean(ttfts), 2) if ttfts else None,
        "prompt_tokens_total": sum(s.prompt_tokens for s in samples),
        "completion_tokens_total": sum(s.completion_tokens for s in samples),
        "prompt_tokens_mean": round(
            statistics.fmean([s.prompt_tokens for s in ok if s.prompt_tokens])
            if any(s.prompt_tokens for s in ok)
            else 0.0,
            1,
        ),
        "estimated_usd": round(sum(s.estimated_usd for s in samples), 6),
        "turns": [asdict(s) for s in samples],
    }


def run_direct(tf_key: str, base_url: str, turns: list[str], spent: list[float], max_usd: float) -> list[TurnSample]:
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {tf_key}", "Content-Type": "application/json"}
    out: list[TurnSample] = []
    for i, user in enumerate(turns):
        if spent[0] >= max_usd:
            break
        body = {
            "model": MODEL,
            "stream": True,
            "stream_options": {"include_usage": True},
            "messages": [
                {"role": "system", "content": SLIM_SYSTEM},
                {"role": "user", "content": user},
            ],
            "max_tokens": 64,
        }
        s = stream_ttft(url=url, headers=headers, body=body)
        s.path = "direct_tf"
        s.turn_idx = i
        spent[0] += s.estimated_usd
        out.append(s)
        print(f"  direct[{i}] ttft={s.ttft_ms:.0f}ms ok={s.ok} usd={s.estimated_usd:.6f}", flush=True)
    return out


def run_hermes(
    tf_key: str,
    base_url: str,
    turns: list[str],
    spent: list[float],
    max_usd: float,
    venv: Path,
) -> list[TurnSample]:
    setup_hermes(tf_key, base_url, venv)
    env = os.environ.copy()
    env["HERMES_HOME"] = str(HERMES_HOME)
    env["API_SERVER_ENABLED"] = "true"
    env["API_SERVER_KEY"] = API_KEY
    env["API_SERVER_HOST"] = "127.0.0.1"
    env["API_SERVER_PORT"] = str(HERMES_PORT)
    env["OPENAI_API_KEY"] = tf_key
    env["OPENAI_BASE_URL"] = base_url.rstrip("/")
    env["PATH"] = str(venv / "bin") + os.pathsep + env.get("PATH", "")

    log = RESULTS / "hermes_gateway.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log_f = log.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [str(venv / "bin" / "hermes"), "gateway", "run", "--accept-hooks"],
        cwd=str(ROOT),
        env=env,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        text=True,
    )
    out: list[TurnSample] = []
    try:
        wait_http(f"http://127.0.0.1:{HERMES_PORT}/health", timeout=180.0)
        time.sleep(1.0)
        url = f"http://127.0.0.1:{HERMES_PORT}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        }
        for i, user in enumerate(turns):
            if spent[0] >= max_usd:
                break
            body = {
                "model": "ignored-unless-direct",
                "stream": True,
                "messages": [
                    {"role": "system", "content": SLIM_SYSTEM},
                    {"role": "user", "content": user},
                ],
            }
            s = stream_ttft(url=url, headers=headers, body=body, timeout=180.0)
            s.path = "hermes_tf"
            s.turn_idx = i
            # Hermes may not forward TF usage; estimate from chars if zero
            if s.prompt_tokens == 0 and s.ok:
                # rough: ~4 chars/token
                approx_in = max(1, (len(SLIM_SYSTEM) + len(user)) // 4)
                approx_out = max(1, len(s.preview) // 4)
                s.prompt_tokens = approx_in
                s.completion_tokens = approx_out
                s.estimated_usd = round(
                    (approx_in * PRICE_IN + approx_out * PRICE_OUT) / 1_000_000.0, 8
                )
            spent[0] += s.estimated_usd
            out.append(s)
            print(f"  hermes[{i}] ttft={s.ttft_ms:.0f}ms ok={s.ok} usd={s.estimated_usd:.6f}", flush=True)
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_f.close()
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get(
            "TOKEN_FACTORY_BASE_URL", "https://api.tokenfactory.nebius.com/v1/"
        ),
    )
    parser.add_argument("--max-usd", type=float, default=1.0)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    tf_key = load_tf_key()
    if not tf_key:
        print("ERROR: set TOKEN_FACTORY_API_KEY", file=sys.stderr)
        return 2

    venv = find_venv()
    turns = TURNS[: args.limit]
    RESULTS.mkdir(parents=True, exist_ok=True)
    spent = [0.0]

    print(f"Model={MODEL} turns={len(turns)} max_usd={args.max_usd} venv={venv}", flush=True)
    print("=== direct Token Factory ===", flush=True)
    direct = run_direct(tf_key, args.base_url, turns, spent, args.max_usd)
    print("=== Hermes → Token Factory ===", flush=True)
    hermes = run_hermes(tf_key, args.base_url, turns, spent, args.max_usd, venv)

    dsum = summarize("direct_tf", direct)
    hsum = summarize("hermes_tf", hermes)
    # Pairwise overhead where both ok
    overheads: list[float] = []
    for a, b in zip(direct, hermes, strict=False):
        if a.ok and b.ok:
            overheads.append(b.ttft_ms - a.ttft_ms)
    overheads_s = sorted(overheads)

    # Design §3.6: Hermes→first token budget 350–450 ms was for local vLLM.
    # With hosted LLM, compare (1) absolute Hermes TTFT to network/TTFT band
    # 0.2–0.8 s plus local Hermes slice, (2) overhead p50 vs 450 ms Hermes-own budget.
    hermes_p50 = hsum["ttft_p50_ms"]
    direct_p50 = dsum["ttft_p50_ms"]
    oh_p50 = round(_pct(overheads_s, 50), 2) if overheads_s else None
    # Pass if Hermes overhead p50 ≤ 450 ms (U2 / S-2 gate on Hermes-added latency)
    gate_overhead_ok = oh_p50 is not None and oh_p50 <= 450.0
    # Absolute Hermes TTFT should sit near measured TF hop (~0.7–3 s on this Mac for chat)
    gate_abs_note = (
        "Hermes absolute TTFT includes Token Factory network; "
        "compare overhead (Hermes−direct) to 450 ms Hermes-own budget."
    )

    summary = {
        "task": "T-M0-03",
        "spike": "S-2",
        "model": MODEL,
        "base_url": args.base_url,
        "n_turns": len(turns),
        "total_estimated_usd": round(spent[0], 6),
        "direct": {k: v for k, v in dsum.items() if k != "turns"},
        "hermes": {k: v for k, v in hsum.items() if k != "turns"},
        "overhead_ms": {
            "n_paired": len(overheads),
            "p50": oh_p50,
            "p95": round(_pct(overheads_s, 95), 2) if overheads_s else None,
            "mean": round(statistics.fmean(overheads), 2) if overheads else None,
        },
        "verdict": {
            "hermes_overhead_p50_le_450ms": gate_overhead_ok,
            "direct_ttft_p50_ms": direct_p50,
            "hermes_ttft_p50_ms": hermes_p50,
            "overhead_p50_ms": oh_p50,
            "design_3_6_note": gate_abs_note,
            "nfr01_context": (
                "NFR-01 p50≤1.8s is end-to-end incl. ASR/TTS; brain+network TTFT "
                "must leave room for endpointing/ASR/TTS (~0.8–1.0s local)."
            ),
        },
        "run_id": str(uuid.uuid4()),
        "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "direct_turns": dsum["turns"],
        "hermes_turns": hsum["turns"],
    }
    out = RESULTS / "ttft_overhead.json"
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in summary if "turns" not in k}, indent=2))
    print(f"Wrote {out}")
    return 0 if gate_overhead_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
