#!/usr/bin/env python3
"""RTT probe from the laptop to Nebius region-facing endpoints.

Uses TCP connect timing and HTTPS TTFB (ICMP is often blocked). Records p50/p95
over N samples. Never sends credentials.
"""

from __future__ import annotations

import argparse
import json
import socket
import ssl
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# Public region-facing hosts suitable for connectivity/RTT sizing (docs.nebius.com).
# Token Factory data-plane hosts are used as stable TCP/TLS endpoints; they are
# NOT the GPU VM itself. Once a VM public IP / WireGuard peer exists, add it via
# --extra host:port.
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
    """TLS handshake + write GET / + read first byte (not full body)."""
    ctx = ssl.create_default_context()
    t0 = time.perf_counter()
    with socket.create_connection((host, port), timeout=timeout_s) as raw:
        with ctx.wrap_socket(raw, server_hostname=host) as sock:
            sock.settimeout(timeout_s)
            req = f"GET / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n"
            sock.sendall(req.encode())
            sock.recv(1)
    return (time.perf_counter() - t0) * 1000.0


def probe_target(
    *,
    host: str,
    port: int,
    samples: int,
    timeout_s: float,
    kind: str,
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
        if kind == "https":
            try:
                https_ms.append(https_ttfb_ms(host, port, timeout_s))
            except OSError:
                https_err += 1
    return {
        "host": host,
        "port": port,
        "kind": kind,
        "tcp_connect": asdict(summarize(tcp_ms, tcp_err)),
        "https_ttfb": asdict(summarize(https_ms, https_err)) if kind == "https" else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--samples", type=int, default=100)
    ap.add_argument("--timeout-s", type=float, default=5.0)
    ap.add_argument(
        "--extra",
        action="append",
        default=[],
        help="Additional host:port (e.g. your GPU public IP:22 or TURN:443)",
    )
    ap.add_argument("--out", type=Path, default=Path("results/rtt.json"))
    args = ap.parse_args()

    targets = list(DEFAULT_TARGETS)
    for item in args.extra:
        host, _, port_s = item.partition(":")
        if not host or not port_s:
            raise SystemExit(f"bad --extra {item!r}; expected host:port")
        targets.append(
            {
                "region": "custom",
                "host": host,
                "port": int(port_s),
                "kind": "tcp",
            }
        )

    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    results = []
    for t in targets:
        print(f"probing {t['region']} {t['host']}:{t['port']} n={args.samples} …", flush=True)
        r = probe_target(
            host=t["host"],
            port=int(t["port"]),
            samples=args.samples,
            timeout_s=args.timeout_s,
            kind=str(t["kind"]),
        )
        r["region"] = t["region"]
        results.append(r)
        tcp = r["tcp_connect"]
        print(
            f"  tcp p50={tcp['p50_ms']}ms p95={tcp['p95_ms']}ms errors={tcp['errors']}",
            flush=True,
        )

    # Prefer us-central1 for LA/Irvine callers when TCP works; else lowest p50.
    ranked = sorted(
        [r for r in results if r["tcp_connect"]["n"] > 0],
        key=lambda r: r["tcp_connect"]["p50_ms"],
    )
    recommendation = ranked[0]["region"] if ranked else None

    report = {
        "spike": "T-M0-07",
        "started_utc": started,
        "client_note": "Run from laptop near Los Angeles / Irvine (design S-6).",
        "samples": args.samples,
        "icmp_note": "ICMP often blocked; TCP/HTTPS used as primary RTT proxy.",
        "targets": results,
        "recommended_region_by_tcp_p50": recommendation,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote {args.out}")
    print(f"recommended_region_by_tcp_p50={recommendation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
