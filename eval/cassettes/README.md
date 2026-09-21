# LLM cassettes (T-M1-13 / ADR-016)

Recorded BrainBackend streams, keyed by SHA-256 of the request messages (+ model).

## Layout

```
eval/cassettes/{hash[:2]}/{hash}.json
```

## Modes

| Mode | When | Behaviour |
|------|------|-----------|
| `replay` (default) | CI, `CALLSCOPE_ENV=test`, or no `--live` | Load cassette; **fail** if missing (no network) |
| `live` / `record` | Explicit `--live` or `CALLSCOPE_LLM_MODE=live` | Call inner backend after `BudgetGuard`; write cassette |

Never commit secrets — fixtures are redacted on save.

## Capture (dev only)

```bash
# after HermesBackend exists (T-M1-09):
CALLSCOPE_ENV=dev CALLSCOPE_LLM_MODE=live uv run python -m ... --live
```

CI must keep `CI=true` / cassette replay only.
