# Optional local LLM fallback (best-effort sketch)

Not a gate for T-M0-04. Prefer Token Factory for the demo agent brain
(D-20260920-12 / ADR-014). If TF is unreachable, a Mac-local OpenAI-compatible
endpoint can be pointed at the same Hermes `provider: custom` slot.

## mlx-lm (recommended sketch on Apple Silicon)

```bash
# illustrative — verify current mlx-lm docs before use
pip install mlx-lm
mlx_lm.server --model <instruct-model-id> --port 8080
```

Hermes `config.yaml` fragment:

```yaml
model:
  provider: custom
  model: <instruct-model-id>
  base_url: http://127.0.0.1:8080/v1
  api_key: local-not-a-secret
```

Constraints on 16 GB unified memory (D-20260920-11): leave ≥4 GB for OS/browser;
ASR+TTS already compete for RAM (T-M0-06). Expect a small quantized instruct
model only; tool-calling quality must be re-measured — do not assume TF scores.

## llama.cpp

```bash
# illustrative
./llama-server -m <gguf> --port 8080
```

Same Hermes custom provider pointing at `http://127.0.0.1:8080/v1`.

## Avoid

Ollama as primary path (Hermes issue V7: `stream=true` with tools hang risk;
D-20260920-13).
