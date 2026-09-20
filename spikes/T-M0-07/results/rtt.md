# RTT results (laptop → Nebius regional HTTPS endpoints)

Captured **2026-09-20T19:00:25Z** from developer laptop (Los Angeles / Irvine area).
Raw JSON: `rtt.json`. ICMP blocked to all targets; metrics are TCP connect + HTTPS TTFB.

| Region | Endpoint | TCP p50 (ms) | TCP p95 (ms) | HTTPS TTFB p50 (ms) | HTTPS TTFB p95 (ms) |
|---|---|---|---|---|---|
| **us-central1** (Kansas City) | `api.tokenfactory.us-central1.nebius.com:443` | **48.9** | **57.1** | 200.5 | 238.3 |
| eu-west1 (France) | `api.tokenfactory.eu-west1.nebius.com:443` | 151.4 | 163.5 | 608.1 | 691.8 |
| eu-north1 (Finland) | `api.tokenfactory.nebius.com:443` | 190.5 | 220.2 | 764.3 | 875.9 |

**Recommendation:** provision the GPU node in **`us-central1`** (lowest TCP p50 by ~3× vs EU).

Caveat: these hosts are Nebius Token Factory data-plane edges, not the VM itself. After the VM exists, re-run:

```bash
python3 scripts/probe_rtt.py --samples 100 --extra "$GPU_PUBLIC_IP:22" --out results/rtt_vm.json
```

WebRTC/TURN probe: deferred until LiveKit is listening on the GPU node (needs provisioned host + ports).
