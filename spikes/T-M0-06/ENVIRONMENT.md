# Environment — T-M0-06 run

- Date (UTC): 2026-09-20
- Host: Apple M5 / 16 GB / macOS arm64
- Spike venv Python: 3.12
- Packages: mlx-whisper, faster-whisper, piper-tts, kokoro-onnx, silero-vad, onnxruntime, jiwer
- ffmpeg: Homebrew 9.0.2
- Probe: `eval/probe/` (30× Albert `say` + C1)
- Parakeet BF16: skipped (>2 GB gate)
