#!/usr/bin/env python3
"""Token Factory regional RTT (TCP/HTTPS) + optional chat-completions TTFT probe.

- Network RTT needs no API key (TCP connect + HTTPS TTFB to public hosts).
- Chat TTFT requires TOKEN_FACTORY_API_KEY or NEBIUS_API_KEY; capped by --max-usd.
Never prints the API key.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import ssl
import statistics
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_TARGETS = [
    {"region": "eu-north1", "host": "api.tokenfactory.nebius.com", "port": 443, "kind": "https"},
    {
        "region": "eu-west1",
        "host": "api.tokenfactory.eu-west1.nebius.com",
        "port": 443,
        "kind": "https",
    },
    {
        "region": "us-central1",
        "host": "api.tokenfactory.us-central1.nebius.com",
        "port": 443,
        "kind": "https",
    },
]

# Cheap function-calling candidate from public catalog (D-20260920-12).
DEFAULT_MODEL = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
# Catalog prices USD / 1M tokens (input, output) for the default model.
DEFAULT_PRICE_IN = 0.06
DEFAULT_PRICE_OUT = 0.24


@dataclass
class SampleStats:
    n: int
    p50_ms: float
    p95_ms: float
    mean_ms: float
    min_ms: float
    max_ms: float
    errors: int


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def summarize(samples_ms: list[float], errors: int) -> SampleStats:
    s = sorted(samples_ms)
    return SampleStats(
        n=len(s),
        p50_ms=round(_percentile(s, 50), 2) if s else float("nan"),
        p95_ms=round(_percentile(s, 95), 2) if s else float("nan"),
        mean_ms=round(statistics.fmean(s), 2) if s else float("nan"),
        min_ms=round(min(s), 2) if s else float("nan"),
        max_ms=round(max(s), 2) if s else float("nan"),
        errors=errors,
    )


def tcp_connect_ms(host: str, port: int, timeout_s: float) -> float:
    t0 = time.perf_counter()
    with socket.create_connection((host, port), timeout=timeout_s):
        pass
    return (time.perf_counter() - t0) * 1000.0


def https_ttfb_ms(host: str, port: int, timeout_s: float) -> float:
    ctx = ssl.create_default_context()
    t0 = time.perf_counter()
    with socket.create_connection((host, port), timeout=timeout_s) as raw:
        with ctx.wrap_socket(raw, server_hostname=host) as sock:
            sock.settimeout(timeout_s)
            req = f"GET / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n"
            sock.sendall(req.encode())
            sock.recv(1)
    return (time.perf_counter() - t0) * 1000.0


def probe_network(
    host: str,
    port: int,
    samples: int,
    timeout_s: float,
    kind: str,
    https_samples: int,
) -> dict[str, Any]:
    tcp_ms: list[float] = []
    https_ms: list[float] = []
    tcp_err = 0
    https_err = 0
    for _ in range(samples):
        try:
            tcp_ms.append(tcp_connect_ms(host, port, timeout_s))
        except OSError:
            tcp_err += 1
    if kind == "https" and https_samples > 0:
        for _ in range(https_samples):
            try:
                https_ms.append(https_ttfb_ms(host, port, timeout_s))
            except OSError:
                https_err += 1
    return {
        "host": host,
        "port": port,
        "kind": kind,
        "tcp_connect": asdict(summarize(tcp_ms, tcp_err)),
        "https_ttfb": asdict(summarize(https_ms, https_err)) if https_ms or https_err else None,
    }


def _api_key() -> str | None:
    return os.environ.get("TOKEN_FACTORY_API_KEY") or os.environ.get("NEBIUS_API_KEY") or None


def estimate_cost_usd(prompt_tokens: int, completion_tokens: int) -> float:
    return (prompt_tokens * DEFAULT_PRICE_IN + completion_tokens * DEFAULT_PRICE_OUT) / 1_000_000.0


def chat_ttft_ms(
    *,
    base_url: str,
    api_key: str,
    model: str,
    timeout_s: float,
) -> tuple[float, int, int]:
    """One non-streaming tiny completion; return (latency_ms, prompt_tokens, completion_tokens)."""
    url = base_url.rstrip("/") + "/chat/completions"
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
            "max_tokens": 4,
            "temperature": 0,
            "stream": False,
        }
    ).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read()
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    data = json.loads(raw.decode())
    usage = data.get("usage") or {}
    return (
        elapsed_ms,
        int(usage.get("prompt_tokens") or 0),
        int(usage.get("completion_tokens") or 0),
    )


def probe_chat(
    *,
    samples: int,
    max_usd: float,
    model: str,
    base_url: str,
    timeout_s: float,
) -> dict[str, Any]:
    key = _api_key()
    if not key:
        return {
            "skipped": True,
            "reason": "TOKEN_FACTORY_API_KEY / NEBIUS_API_KEY not set",
        }
    # Pre-estimate: assume ~20 prompt + 2 completion tokens per call
    projected = estimate_cost_usd(20, 2) * samples
    if projected > max_usd:
        return {
            "skipped": True,
            "reason": f"projected ${projected:.6f} exceeds --max-usd {max_usd}",
            "projected_usd": projected,
        }

    latencies: list[float] = []
    errors = 0
    prompt_tokens = 0
    completion_tokens = 0
    spend = 0.0
    for i in range(samples):
        if spend >= max_usd:
            break
        try:
            ms, pt, ct = chat_ttft_ms(
                base_url=base_url, api_key=key, model=model, timeout_s=timeout_s
            )
            latencies.append(ms)
            prompt_tokens += pt
            completion_tokens += ct
            spend += estimate_cost_usd(pt, ct)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            errors += 1
            if i == 0:
                return {
                    "skipped": False,
                    "fatal_error": type(exc).__name__,
                    "detail": str(exc)[:200],
                    "completed": 0,
                }
    return {
        "skipped": False,
        "model": model,
        "base_url": base_url,
        "requested_samples": samples,
        "completed": len(latencies),
        "latency_ms": asdict(summarize(latencies, errors)),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "estimated_spend_usd": round(spend, 6),
        "max_usd": max_usd,
        "note": "Non-streaming end-to-end latency (not true SSE TTFT); good network+queue proxy.",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--samples", type=int, default=100, help="TCP connect samples per region")
    ap.add_argument(
        "--https-samples",
        type=int,
        default=20,
        help="HTTPS TTFB samples per region (cheaper than matching TCP count)",
    )
    ap.add_argument("--timeout-s", type=float, default=30.0)
    ap.add_argument("--out", type=Path, default=Path("results/tf_latency.json"))
    ap.add_argument("--skip-network", action="store_true")
    ap.add_argument("--skip-chat", action="store_true")
    ap.add_argument("--max-usd", type=float, default=0.25, help="Hard spend cap for chat probes")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument(
        "--base-url",
        default=os.environ.get("TOKEN_FACTORY_BASE_URL", "https://api.tokenfactory.nebius.com/v1"),
    )
    args = ap.parse_args()

    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    network: list[dict[str, Any]] = []
    if not args.skip_network:
        for t in DEFAULT_TARGETS:
            print(
                f"probing {t['region']} {t['host']}:{t['port']} "
                f"tcp_n={args.samples} https_n={args.https_samples} …",
                flush=True,
            )
            r = probe_network(
                host=str(t["host"]),
                port=int(t["port"]),
                samples=args.samples,
                timeout_s=min(args.timeout_s, 3.0),
                kind=str(t["kind"]),
                https_samples=args.https_samples,
            )
            r["region"] = t["region"]
            network.append(r)
            tcp = r["tcp_connect"]
            print(f"  tcp p50={tcp['p50_ms']}ms p95={tcp['p95_ms']}ms", flush=True)
            if r.get("https_ttfb"):
                h = r["https_ttfb"]
                print(f"  https p50={h['p50_ms']}ms p95={h['p95_ms']}ms", flush=True)

    ranked = sorted(
        [r for r in network if r["tcp_connect"]["n"] > 0],
        key=lambda r: r["tcp_connect"]["p50_ms"],
    )
    recommendation = ranked[0]["region"] if ranked else None

    chat: dict[str, Any]
    if args.skip_chat:
        chat = {"skipped": True, "reason": "--skip-chat"}
    else:
        print(f"chat probe model={args.model} n={args.samples} max_usd={args.max_usd} …", flush=True)
        chat = probe_chat(
            samples=args.samples,
            max_usd=args.max_usd,
            model=args.model,
            base_url=args.base_url,
            timeout_s=args.timeout_s,
        )
        print(json.dumps({k: chat[k] for k in chat if k != "detail"}, indent=2), flush=True)

    report = {
        "spike": "T-M0-07",
        "started_utc": started,
        "samples": args.samples,
        "network": network,
        "recommended_region_by_tcp_p50": recommendation,
        "chat": chat,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    print(f"recommended_region_by_tcp_p50={recommendation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
