"""Provider interfaces and shared helpers (budget, mocks, backends)."""

from __future__ import annotations

from callscope.providers.asr_client import ASRClient
from callscope.providers.base import (
    BrainBackend,
    BrainDelta,
    Msg,
    ProviderError,
    ProviderTimeout,
    ProviderUnavailable,
    STTEvent,
    STTProvider,
    ToolEvent,
    Transcript,
    TTSProvider,
    WordTiming,
)
from callscope.providers.budget import (
    BudgetExceededError,
    BudgetGuard,
    BudgetStatus,
    ModelPrice,
    cost_from_usage,
    estimate_usd,
)
from callscope.providers.cassettes import (
    CassetteBrain,
    CassetteError,
    CassetteMissingError,
    CassetteMode,
    CassetteStore,
    request_hash,
    resolve_mode,
)
from callscope.providers.hermes_backend import HermesBackend, inject_call_context
from callscope.providers.mock import MockBrain, MockSTT, MockTTS
from callscope.providers.tts_client import TTSClient

__all__ = [
    "ASRClient",
    "BrainBackend",
    "BrainDelta",
    "BudgetExceededError",
    "BudgetGuard",
    "BudgetStatus",
    "CassetteBrain",
    "CassetteError",
    "CassetteMissingError",
    "CassetteMode",
    "CassetteStore",
    "HermesBackend",
    "MockBrain",
    "MockSTT",
    "MockTTS",
    "ModelPrice",
    "Msg",
    "ProviderError",
    "ProviderTimeout",
    "ProviderUnavailable",
    "STTEvent",
    "STTProvider",
    "TTSClient",
    "TTSProvider",
    "ToolEvent",
    "Transcript",
    "WordTiming",
    "cost_from_usage",
    "estimate_usd",
    "inject_call_context",
    "request_hash",
    "resolve_mode",
]
