"""Run: ``python -m servers.asr`` (uvicorn)."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("CALLSCOPE_ASR_HOST", "127.0.0.1")
    port = int(os.environ.get("CALLSCOPE_ASR_PORT", "8200"))
    uvicorn.run("servers.asr.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
