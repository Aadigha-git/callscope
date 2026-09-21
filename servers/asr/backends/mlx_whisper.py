"""Optional mlx-whisper backend (lazy import; not loaded in CI)."""

from __future__ import annotations

from typing import Any, cast

from servers.asr.backends.base import ASRFinal, ASRSessionState, WordTiming


class MlxWhisperBackend:
    """Whisper-tiny via mlx-whisper — load only when selected at runtime."""

    name = "mlx_whisper"

    def __init__(self, model_id: str = "mlx-community/whisper-tiny") -> None:
        self._model_id = model_id
        self._model: Any = None

    def load(self) -> None:
        try:
            import mlx_whisper as mw
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "mlx-whisper is not installed; use CALLSCOPE_ASR_BACKEND=fake for CI"
            ) from exc
        self._model = mw

    def begin(self, *, sample_rate: int, hotwords: list[str] | None) -> ASRSessionState:
        if self._model is None:
            self.load()
        return ASRSessionState(sample_rate=sample_rate, hotwords=list(hotwords or []))

    def transcribe_chunk(self, state: ASRSessionState, pcm: bytes) -> str | None:
        state.pcm.extend(pcm)
        return None

    def finalize(self, state: ASRSessionState) -> ASRFinal:  # pragma: no cover - gpu
        if self._model is None:
            self.load()
        import numpy as np

        audio = np.frombuffer(bytes(state.pcm), dtype=np.int16).astype(np.float32) / 32768.0
        # Hotwords → Whisper initial_prompt (biasing; not a hard lexicon).
        initial = " ".join(state.hotwords) if state.hotwords else None
        mw = cast(Any, self._model)
        result = mw.transcribe(
            audio,
            path_or_hf_repo=self._model_id,
            word_timestamps=True,
            initial_prompt=initial,
        )
        text = str(result.get("text", "")).strip()
        words_out: list[WordTiming] = []
        for seg in result.get("segments") or []:
            for w in seg.get("words") or []:
                words_out.append(
                    WordTiming(
                        w=str(w.get("word", "")).strip(),
                        start_ms=int(float(w.get("start", 0)) * 1000),
                        end_ms=int(float(w.get("end", 0)) * 1000),
                        conf=float(w["probability"]) if "probability" in w else None,
                    )
                )
        if not words_out and text:
            words_out = [
                WordTiming(w=tok, start_ms=i * 200, end_ms=i * 200 + 180, conf=None)
                for i, tok in enumerate(text.split())
            ]
        avg = None
        confs = [w.conf for w in words_out if w.conf is not None]
        if confs:
            avg = sum(confs) / len(confs)
        return ASRFinal(
            text=text,
            words=tuple(words_out),
            avg_conf=avg,
            audio_ms=int(len(state.pcm) / 2 / max(state.sample_rate, 1) * 1000),
        )
