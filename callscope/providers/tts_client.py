"""TTSProvider client over the TTS server HTTP chunked stream (design §4.3)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from callscope.providers.base import ProviderError, ProviderUnavailable


class TTSClient:
    """httpx streaming client implementing ``TTSProvider``."""

    def __init__(
        self,
        base_url: str,
        *,
        sample_rate: int = 24_000,
        timeout_s: float = 60.0,
        default_voice: str = "default",
    ) -> None:
        self._base = base_url.rstrip("/")
        self.sample_rate = sample_rate
        self._timeout = timeout_s
        self._default_voice = default_voice

    async def stream(self, text: str, *, voice: str, speed: float) -> AsyncIterator[bytes]:
        url = f"{self._base}/v1/tts/stream"
        payload = {
            "text": text,
            "voice": voice or self._default_voice,
            "speed": speed,
            "sample_rate": self.sample_rate,
        }
        try:
            async with (
                httpx.AsyncClient(timeout=self._timeout) as client,
                client.stream("POST", url, json=payload) as resp,
            ):
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", errors="replace")
                    raise ProviderError(f"TTS HTTP {resp.status_code}: {body}")
                hdr_sr = resp.headers.get("x-sample-rate")
                if hdr_sr is not None:
                    self.sample_rate = int(hdr_sr)
                async for chunk in resp.aiter_bytes():
                    if chunk:
                        yield chunk
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderUnavailable(f"TTS stream failed: {exc}") from exc

    async def voices(self) -> list[dict[str, object]]:
        url = f"{self._base}/v1/voices"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            raise ProviderUnavailable(f"TTS voices failed: {exc}") from exc
        return list(data.get("voices") or [])
