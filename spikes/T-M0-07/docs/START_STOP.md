# GPU node start / stop procedure (input to T-M6-03)

Spike S-6 draft. Update with the real Nebius project ID, region, VM name, and
disk IDs after provisioning. **Never commit credentials or SSH private keys.**

## Goals

- GPU node is **on-demand** (ADR-009): start for demo/spikes, stop when idle.
- Model weights live on a **persistent disk** so warm start is minutes, not a full re-download.
- Control from the laptop / CPU node over SSH (or Nebius CLI) using keys stored only on the operator machine / GitHub Environment secrets.

## One-time provisioning (human)

1. Create Nebius project in the region chosen by RTT (`results/rtt.json`).
2. Create a GPU VM matching design §9.2 starting point (refine after S-6 numbers):
   - Prefer **24–48 GB class** single GPU for cost (e.g. L40S if available in region), else H100/H200 only if needed.
   - 8+ vCPU, 32–64 GB RAM, boot disk ≥ 50 GB.
3. Create a **persistent disk** ≥ 200 GB NVMe/SSD; mount at `/var/lib/callscope/models`.
4. Attach a firewall profile: SSH from your IP / Tailscale only; no public model ports.
5. Install drivers + Docker via `scripts/bootstrap_gpu_node.sh` (set `CONFIRM_INSTALL=1` only after reading NVIDIA toolkit docs for the image).
6. Record (privately): `VM_ID`, `DISK_ID`, `REGION`, `SSH_HOST`, `SSH_USER`.

Suggested `/etc/fstab` entry (example — adjust UUID):

```
UUID=<disk-uuid>  /var/lib/callscope/models  ext4  defaults,nofail  0  2
```

## Start (warm path)

```bash
# From laptop — replace with Nebius CLI or console equivalent once provisioned.
# nebius compute instance start --id "$VM_ID"

ssh "$SSH_USER@$SSH_HOST" 'bash -s' < scripts/bootstrap_gpu_node.sh
ssh "$SSH_USER@$SSH_HOST" 'df -h /var/lib/callscope/models && nvidia-smi'

# Later (T-M1-11 / T-M6-03): docker compose -f docker-compose.gpu.yml up -d
# Health-wait, then smoke.
```

Measure wall-clock from `instance start` → `nvidia-smi` ready → models loaded; record in `results/warmup.md`.

## Stop

```bash
# Drain sessions / compose down first when stack exists.
# nebius compute instance stop --id "$VM_ID"
```

Confirm billing shows compute stopped; **do not** delete the persistent model disk.

## Idle auto-shutdown (T-M6-03)

Design target: stop when zero sessions for 30 minutes (NFR-07 / §9.7). This spike only documents the manual path; automation lands in T-M6-03.

## Rollback / failure

| Symptom | Action |
|---|---|
| VM won't start | Check quota/region capacity; try alternate region from RTT table |
| Cache disk missing | Re-attach disk; do not recreate empty volume unless intentional |
| CUDA / driver mismatch | Re-run bootstrap; pin driver version in DECISIONS |
| Credits burning | `instance stop` immediately; rotate keys if exposed |

## Secrets

| Secret | Where |
|---|---|
| Nebius API token / IAM | Operator password manager or GH Environment `staging` — never git |
| SSH deploy key | `~/.ssh/id_deploy` (see `scripts/deploy.sh`) — never git |
| Model HF token (if gated) | Node `/opt/callscope/.env` mode 600 |
