# Spike T-M0-07 — GPU sizing, warm-up, RTT (S-6)

Throwaway harness under `spikes/T-M0-07/`. Do not import into `callscope/`.
Never print or commit credentials, SSH keys, or Nebius tokens.

## Ownership split (from task prompt)

| Who | What |
|---|---|
| Human | Provision Nebius GPU VM + persistent model-cache disk; provide SSH host |
| Agent | Scripts, RTT probe from laptop, start/stop procedure, fill results once node exists |

## Layout

| Path | Role |
|---|---|
| `scripts/bootstrap_gpu_node.sh` | Docker + NVIDIA toolkit checks; print `nvidia-smi` |
| `scripts/measure_vram.py` | Cold/warm model load timings + VRAM via `nvidia-smi` |
| `scripts/probe_rtt.py` | ICMP / TCP / HTTPS RTT from laptop (p50/p95, n=100) |
| `docs/START_STOP.md` | VM start/stop + persistent cache (input to T-M6-03) |
| `results/` | Measured tables (committed scrubbed only) |

## Quick start

### 1. Laptop RTT (no GPU required)

```bash
cd spikes/T-M0-07
python3 scripts/probe_rtt.py --samples 100 --out results/rtt.json
```

### 2. On the GPU node (after you provision)

```bash
# copy spike folder or clone repo
bash scripts/bootstrap_gpu_node.sh | tee results/bootstrap.txt
# configure model IDs via env (see measure_vram.py --help), then:
python3 scripts/measure_vram.py --out results/vram.json
```

### 3. Record decision

Update `docs/DECISIONS.md` + design §9.5 with measured numbers; keep secrets out of git.
