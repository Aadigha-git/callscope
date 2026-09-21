"""Run: ``python -m servers.tts`` (uvicorn)."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("CALLSCOPE_TTS_HOST", "127.0.0.1")
    port = int(os.environ.get("CALLSCOPE_TTS_PORT", "8300"))
    uvicorn.run("servers.tts.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
