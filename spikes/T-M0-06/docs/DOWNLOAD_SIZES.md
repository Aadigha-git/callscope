# Planned downloads (T-M0-06)

All candidates below are **under 2 GB**. No download >2 GB without an explicit size notice.

| Asset | Approx size | Notes |
|---|---:|---|
| mlx-community whisper-tiny / whisper-base (via mlx-whisper) | ~75–150 MB each | MIT code; Whisper weights MIT |
| mlx-community/parakeet-tdt-0.6b-v3 **int8** (if available) else skip BF16 | ~0.8 GB (int8) / **~2.5 GB BF16 — skipped** | CC-BY-4.0 weights |
| Silero VAD ONNX | ~2 MB | |
| Kokoro ONNX (voices) | ~330 MB | Apache-2.0 weights |
| Piper `en_US-lessac-medium` | ~61 MB | GPL-3.0-or-later caution |
| faster-whisper tiny/base CTranslate2 | ~75–150 MB | CPU path |

**Skipped (>2 GB or out of RAM budget):** Whisper large/turbo, Parakeet BF16 2.51 GB, local LLM.
