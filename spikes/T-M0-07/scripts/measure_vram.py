#!/usr/bin/env python3
"""Measure cold/warm model load time and VRAM for placeholder ASR/TTS/LLM services.

Run on the GPU node with CUDA visible. Does NOT invent VRAM numbers — records
nvidia-smi queries around real load steps.

Default model IDs are small stand-ins suitable for a sizing probe; override via
env or flags before spending bandwidth/credits. Never logs tokens or secrets.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class GpuSample:
    t_unix: float
    name: str
    memory_total_mib: float
    memory_used_mib: float
    memory_free_mib: float
    utilization_gpu: float


def _nvidia_query() -> GpuSample:
    out = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        text=True,
    ).strip()
    # Multi-GPU: use first device for this spike (single-GPU node expected).
    line = out.splitlines()[0]
    parts = [p.strip() for p in line.split(",")]
    return GpuSample(
        t_unix=time.time(),
        name=parts[0],
        memory_total_mib=float(parts[1]),
        memory_used_mib=float(parts[2]),
        memory_free_mib=float(parts[3]),
        utilization_gpu=float(parts[4]),
    )


def _run(cmd: list[str], *, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, env=env)


def measure_phase(label: str, fn) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    before = _nvidia_query()
    t0 = time.perf_counter()
    fn()
    elapsed_s = time.perf_counter() - t0
    after = _nvidia_query()
    return {
        "label": label,
        "elapsed_s": round(elapsed_s, 3),
        "vram_before_mib": before.memory_used_mib,
        "vram_after_mib": after.memory_used_mib,
        "vram_delta_mib": round(after.memory_used_mib - before.memory_used_mib, 1),
        "gpu": asdict(after),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--cache-dir",
        default=os.environ.get("CALLSCOPE_MODEL_CACHE", "/var/lib/callscope/models"),
    )
    p.add_argument(
        "--mode",
        choices=("probe-idle", "torch-alloc", "full"),
        default="probe-idle",
        help="probe-idle: nvidia-smi only; torch-alloc: allocate N GiB; full: reserved for container loads",
    )
    p.add_argument("--alloc-gib", type=float, default=1.0, help="for torch-alloc mode")
    p.add_argument("--out", type=Path, default=Path("results/vram.json"))
    args = p.parse_args()

    if shutil.which("nvidia-smi") is None:
        raise SystemExit("nvidia-smi not found — run on the GPU node")

    cache = Path(args.cache_dir)
    cache.mkdir(parents=True, exist_ok=True)

    idle = _nvidia_query()
    report: dict[str, Any] = {
        "spike": "T-M0-07",
        "mode": args.mode,
        "cache_dir": str(cache),
        "idle": asdict(idle),
        "phases": [],
        "notes": [],
    }

    if args.mode == "probe-idle":
        report["notes"].append(
            "Idle baseline only. Re-run with --mode torch-alloc or --mode full after "
            "vLLM/ASR/TTS containers are defined (T-M1-05/06 + S-3/S-5 shortlist)."
        )
    elif args.mode == "torch-alloc":
        def _alloc() -> None:
            import torch  # local import — only on GPU node

            if not torch.cuda.is_available():
                raise RuntimeError("torch.cuda not available")
            n = int(args.alloc_gib * (1024**3) / 4)  # float32 elements
            t = torch.empty((n,), device="cuda", dtype=torch.float32)
            torch.cuda.synchronize()
            del t
            torch.cuda.empty_cache()

        # Cold: first alloc; warm: second alloc after empty_cache
        report["phases"].append(measure_phase("torch_alloc_cold", _alloc))
        report["phases"].append(measure_phase("torch_alloc_warm", _alloc))
        report["notes"].append(
            "torch-alloc is a harness self-test, not production model VRAM. "
            "Replace with real vLLM/ASR/TTS loads once shortlist exists."
        )
    else:  # full
        report["notes"].append(
            "full mode placeholder: wire docker run lines for vLLM + ASR + TTS "
            "once S-3/S-5 choose models. Record each service start as a phase."
        )
        # Example structure operators fill by editing env:
        # CALLSCOPE_VLLM_IMAGE, CALLSCOPE_ASR_IMAGE, CALLSCOPE_TTS_IMAGE
        for svc, env_key in (
            ("vllm", "CALLSCOPE_VLLM_IMAGE"),
            ("asr", "CALLSCOPE_ASR_IMAGE"),
            ("tts", "CALLSCOPE_TTS_IMAGE"),
        ):
            image = os.environ.get(env_key, "")
            if not image:
                report["notes"].append(f"skip {svc}: set {env_key}")
                continue

            def _load(img: str = image, name: str = svc) -> None:
                _run(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "--gpus",
                        "all",
                        "-e",
                        f"HF_HOME={cache}",
                        "-v",
                        f"{cache}:{cache}",
                        img,
                        "true",
                    ]
                )

            report["phases"].append(measure_phase(f"{svc}_container_start", _load))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
