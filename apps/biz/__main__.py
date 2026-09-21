"""python -m apps.biz"""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("CALLSCOPE_BIZ_HOST", "127.0.0.1")
    port = int(os.environ.get("CALLSCOPE_BIZ_PORT", "8100"))
    uvicorn.run("apps.biz.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
