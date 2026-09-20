# T-M0-06 / S-5 SUMMARY — Apple Silicon ASR/TTS/VAD shortlist

**Host:** Apple M5 / 16 GB (see D-20260920-11 / T-M0-07)
**Probe:** 30 synthetic utterances (`eval/probe/`, macOS `say` Albert) · C0 clean + C1 telephony
**Skipped >2 GB:** Parakeet BF16 (~2.5 GB). ffmpeg installed via Homebrew for audio decode.

## Shortlist (decision)

| Role | Choice | Licence | Why |
|---|---|---|---|
| ASR #1 | **mlx-whisper** `mlx-community/whisper-tiny` | MIT | Best RTF on Metal (~0.03 mean C0); low memory after load |
| ASR #2 | **faster-whisper** `tiny`/`base` → prefer **base** | MIT | Best WER on this probe among candidates; CPU fallback if MLX path regresses |
| TTS #1 | **Piper** `en_US-lessac-medium` | GPL-3.0-or-later | first-audio p50 **53 ms**, RTF ~0.03; licence caution for redistribution |
| TTS #2 | **kokoro-onnx** v1.0 | Apache-2.0 | Safer redistribution licence; first-audio ≈611 ms (non-stream `create`) |
| VAD | **Silero** (`silero-vad` pip / LiveKit Agents) | MIT | p50 ~8 ms / utterance; already proven in T-M0-05 |

## Measured numbers (30 utts)

### ASR (WER raw vs spoken-digit references — orthography-sensitive; use for ranking)

| Engine / model | Cond | WER | RTF mean | RTF p95 | ΔRSS MB |
|---|---|---:|---:|---:|---:|
| mlx-whisper tiny | C0 | 0.74 | 0.030 | 0.068 | ~203 (incl. load) |
| mlx-whisper tiny | C1 | 0.85 | 0.043 | 0.127 | ~2 |
| mlx-whisper base.en-mlx | C0 | 0.88 | 0.151 | 0.124 | ~261 (incl. load) |
| mlx-whisper base.en-mlx | C1 | 1.04 | 0.030 | 0.085 | ~3 |
| faster-whisper tiny | C0 | 0.72 | 0.080 | 0.183 | ~208 |
| faster-whisper tiny | C1 | 0.83 | 0.161 | 0.541 | ~26 |
| faster-whisper base | C0 | **0.69** | 0.175 | 0.477 | ~46 |
| faster-whisper base | C1 | **0.74** | 0.176 | 0.303 | ~77 |

Streaming: none of the Whisper paths are natively streaming → **VAD-segmented chunking** for the worker.

### TTS

| Engine | first-audio p50 / p95 | RTF mean | ΔRSS MB |
|---|---:|---:|---:|
| Piper lessac-medium | **53 / 125 ms** | 0.028 | ~67 |
| kokoro-onnx | 611 / 939 ms | 0.260 | ~91 |

### VAD

Silero (`silero-vad` 6.2.2): mean speech ratio ~0.55 on C0 probe; latency p50 **8.3 ms**; ΔRSS ~11 MB.

## E2 LoRA feasibility

whisper-tiny/base MLX working-set fits in the ~12 GB usable budget with ASR+TTS. **Defer E2** (T-M5-05 optional) until a real telephony-augmented train set exists — synthetic `say` audio is not a training corpus.

## Raw

`results/benchmark.json` · `docs/DOWNLOAD_SIZES.md` · `eval/probe/`
