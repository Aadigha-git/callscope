"""CLI: ``python -m callscope.devtools.review_cli seed-demo``."""

from __future__ import annotations

import argparse
import os
import sys

from apps.review.api_client import ReviewApiClient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="callscope-review")
    sub = parser.add_subparsers(dest="cmd", required=True)
    seed = sub.add_parser("seed-demo", help="Seed N synthetic flagged/labelled calls via API")
    seed.add_argument("--n", type=int, default=40)
    seed.add_argument(
        "--api-url",
        default=os.environ.get("CALLSCOPE_API_URL", "http://127.0.0.1:8000"),
    )
    seed.add_argument(
        "--token",
        default=os.environ.get("CALLSCOPE_SERVICE_TOKEN", "changeme-service-token"),
    )
    args = parser.parse_args(argv)
    if args.cmd == "seed-demo":
        client = ReviewApiClient(args.api_url, args.token)
        try:
            res = client.seed_demo(args.n)
        finally:
            client.close()
        print(f"created={res['created']} labelled={res['labelled']}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
