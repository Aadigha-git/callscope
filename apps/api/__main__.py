"""Run: ``python -m apps.api``."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("CALLSCOPE_API_HOST", "127.0.0.1")
    port = int(os.environ.get("CALLSCOPE_API_PORT", "8000"))
    uvicorn.run("apps.api.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
