"""Deterministic fake ASR backend for CI (no model weights)."""

from __future__ import annotations

from servers.asr.backends.base import ASRFinal, ASRSessionState, WordTiming


class FakeASRBackend:
    """Maps audio duration + optional hotwords to a scripted transcript."""

    name = "fake"

    def __init__(self, *, default_text: str = "hello from fake asr") -> None:
        self._default_text = default_text
        self._loaded = False

    def load(self) -> None:
        self._loaded = True

    def begin(self, *, sample_rate: int, hotwords: list[str] | None) -> ASRSessionState:
        if not self._loaded:
            self.load()
        return ASRSessionState(sample_rate=sample_rate, hotwords=list(hotwords or []))

    def transcribe_chunk(self, state: ASRSessionState, pcm: bytes) -> str | None:
        state.pcm.extend(pcm)
        # Partial grows with buffered duration (local-agreement style).
        audio_ms = _pcm_ms(len(state.pcm), state.sample_rate)
        words = self._text_for(state).split()
        n = max(1, min(len(words), audio_ms // 200 + 1))
        partial = " ".join(words[:n])
        if partial == state.last_partial:
            return None
        state.last_partial = partial
        return partial

    def finalize(self, state: ASRSessionState) -> ASRFinal:
        text = self._text_for(state)
        audio_ms = _pcm_ms(len(state.pcm), state.sample_rate)
        words = tuple(
            WordTiming(
                w=w,
                start_ms=i * 200,
                end_ms=i * 200 + 180,
                conf=0.9,
            )
            for i, w in enumerate(text.split())
        )
        return ASRFinal(text=text, words=words, avg_conf=0.9, audio_ms=audio_ms)

    def _text_for(self, state: ASRSessionState) -> str:
        if state.hotwords:
            return " ".join(state.hotwords)
        return self._default_text


def _pcm_ms(nbytes: int, sample_rate: int) -> int:
    if sample_rate <= 0:
        return 0
    return int(nbytes / 2 / sample_rate * 1000)
