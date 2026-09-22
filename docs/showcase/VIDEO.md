# CallScope demo video — recording script

**Status:** Script ready. Binary recording is an operator step (screen capture on this Mac
during a real `make demo` run). Place the file at `docs/showcase/assets/demo.mp4` or attach
it to the GitHub release (D-20260922-47).

## Setup before record

1. Quit heavy apps; silence notifications.
2. `make demo` with preferred backends (fake for reliable audio smoke, or mlx/piper for realism).
3. Browser window only: http://127.0.0.1:5173 (hide bookmarks bar).
4. Optional second window: Grafana Live-ops cropped.
5. Start screen + system audio capture (QuickTime / OBS), 1080p, ≤5 minutes.

## Shot list (target 2:00–3:00)

| T | Visual | Narration |
|---|--------|-----------|
| 0:00 | Showcase homepage or repo title | “CallScope — local voice agent eval on Apple Silicon.” |
| 0:15 | Consent banner | “Consent and fictional-data banner before any token.” |
| 0:30 | Live call — book Friday | “Cascaded STT → Hermes/Token Factory → TTS; session cap 2.” |
| 1:00 | Barge-in | “Barge-in stops playback within the oracle budget.” |
| 1:20 | Grafana | “Worker is latency SoT; stages on the Live-ops board.” |
| 1:40 | Showcase eval / model card | “Frozen-test improvements E1/E3; cards and lifecycle gates.” |
| 2:10 | End | “Reproduce offline with mocks + cassettes; live demo via make demo.” |

## After record

```bash
mkdir -p docs/showcase/assets
# mv ~/Desktop/callscope-demo.mp4 docs/showcase/assets/demo.mp4
# Update docs/showcase/index.html video src if needed
```

Do **not** commit real personal audio or production API keys.
