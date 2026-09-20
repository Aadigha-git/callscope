#!/usr/bin/env python3
"""Mac baseline + idle unified-memory snapshot for CallScope S-6 (T-M0-07).

No model downloads. Records chip/RAM and a rough memory picture so §9.5 can
reserve ≥4 GB for OS/browser and leave placeholders for ASR/TTS (filled by S-5).
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import time
from pathlib import Path


def _sysctl(name: str) -> str:
    return subprocess.check_output(["sysctl", "-n", name], text=True).strip()


def _sw_vers() -> dict[str, str]:
    out = subprocess.check_output(["sw_vers"], text=True)
    return dict(line.split(":\t", 1) for line in out.strip().splitlines() if ":\t" in line)


def _vm_pages() -> dict[str, int]:
    raw = subprocess.check_output(["vm_stat"], text=True)
    page_size = 16384
    for line in raw.splitlines():
        if "page size of" in line:
            # "Mach Virtual Memory Statistics: (page size of 16384 bytes)"
            try:
                page_size = int(line.split("page size of")[1].split()[0])
            except (IndexError, ValueError):
                pass
    pages: dict[str, int] = {}
    for line in raw.splitlines():
        if ":" not in line or line.startswith("Mach"):
            continue
        key, _, rest = line.partition(":")
        num = rest.strip().rstrip(".").replace(",", "")
        if num.isdigit():
            pages[key.strip()] = int(num)
    return {"page_size_bytes": page_size, **pages}


def main() -> int:
    page = _vm_pages()
    page_size = int(page["page_size_bytes"])
    total_bytes = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    free_pages = int(page.get("Pages free", 0))
    purgeable = int(page.get("Pages purgeable", 0))
    speculative = int(page.get("Pages speculative", 0))
    # Conservative "available-ish" estimate: free + purgeable + speculative
    avail_bytes = (free_pages + purgeable + speculative) * page_size
    reserve_os_browser_gb = 4.0
    usable_for_models_gb = max(0.0, total_bytes / (1024**3) - reserve_os_browser_gb)

    report = {
        "spike": "T-M0-07",
        "captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "chip": _sysctl("machdep.cpu.brand_string"),
        "arch": platform.machine(),
        "ram_bytes": total_bytes,
        "ram_gb": round(total_bytes / (1024**3), 2),
        "sw_vers": _sw_vers(),
        "reserve_os_browser_gb": reserve_os_browser_gb,
        "usable_for_models_gb_estimate": round(usable_for_models_gb, 2),
        "vm_stat": page,
        "approx_free_plus_purgeable_gb": round(avail_bytes / (1024**3), 2),
        "notes": [
            "Docker Desktop on Mac cannot use Metal; ASR/TTS must run natively.",
            "ASR/TTS/VAD memory numbers are deferred to T-M0-06 (S-5) — do not download >2 GB here.",
            "Optional local LLM fallback may not fit with ASR+TTS on 16 GB; Token Factory is primary.",
        ],
        "memory_budget_plan": {
            "ASR (candidate)": "measure in T-M0-06",
            "TTS (candidate)": "measure in T-M0-06",
            "VAD (Silero)": "measure in T-M0-06 / LiveKit Agents",
            "Hermes + worker + APIs": "measure when walking skeleton runs",
            "Optional local LLM": "best-effort; likely deferred on 16 GB",
            "Headroom": f">={reserve_os_browser_gb} GB reserved OS/browser",
        },
    }
    out = Path(__file__).resolve().parents[1] / "results" / "mac_baseline.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("chip", "arch", "ram_gb", "usable_for_models_gb_estimate", "approx_free_plus_purgeable_gb")}, indent=2))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
