# Probe audio (T-M0-06 / S-5)

Synthetic Lakeside receptionist utterances for ASR/TTS/VAD shortlisting.

- **Source:** macOS `say` (Albert) — not personal recordings
- **C0:** 16 kHz clean WAV
- **C1:** telephony chain (band 300–3400 Hz, 8 kHz μ-law round-trip → 16 kHz)
- **Regenerate:** `bash eval/probe/scripts/generate_probe_audio.sh`
  (implementation: `spikes/T-M0-06/scripts/generate_probe_audio.py`)

Benchmark harness: `spikes/T-M0-06/scripts/run_benchmark.py`.
