# Spike T-M0-06 — Apple Silicon ASR/TTS/VAD shortlist (S-5)

Native (non-Docker) probe of ASR/TTS/VAD candidates for the local Mac demo.

## Rerun

```bash
cd spikes/T-M0-06
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
# needs ffmpeg on PATH (brew install ffmpeg) and macOS `say`
python ../../eval/probe/scripts/generate_probe_audio.py   # if audio missing
.venv/bin/python scripts/run_benchmark.py --limit 30 --skip parakeet
```

See `docs/DOWNLOAD_SIZES.md` before enabling Parakeet BF16 (~2.5 GB).

## Deliverables

- `results/SUMMARY.md` + `results/benchmark.json`
- Probe assets: `eval/probe/`
- Decision: D-20260920-19
