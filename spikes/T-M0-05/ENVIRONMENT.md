# Environment — T-M0-05 / S-4

Captured 2026-09-20 during spike run.

| Item | Value |
|---|---|
| Host OS | macOS (darwin 25.6.0), arm64 |
| Python (spike venv) | 3.12.13 |
| livekit-agents | 1.8.2 |
| livekit | 1.1.18 |
| livekit-api | 1.2.1 |
| livekit.plugins.silero | 1.8.2 (bundled extra) |
| livekit-server image | livekit/livekit-server:v1.9.1 |
| Dev API key/secret | `devkey` / `secret` (server `--dev` placeholders) |
| hermes-livekit reviewed | 0.4.0, commit `640812f` (2026-09-13), MIT |
| Smoke room | `callscope-spike-2` |
| Smoke result | `SMOKE_OK agent_audio_subscribed` (see `results/evidence.md`) |

APIs verified from installed package source under
`.venv/lib/python3.12/site-packages/livekit/agents/` (not invented).
