"""Deterministic seed entrypoint for Lakeside Home Services."""

from __future__ import annotations

import argparse
import json

from apps.biz.store import seed_store


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Print Lakeside seed fingerprint")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args(argv)
    store = seed_store(args.seed)
    print(
        json.dumps(
            {
                "seed": store.seed,
                "fingerprint": store.fingerprint(),
                "services": len(store.services),
                "slots": len(store.slots),
                "kb_docs": len(store.kb),
            }
        )
    )


if __name__ == "__main__":
    main()
