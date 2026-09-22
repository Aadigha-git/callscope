"""Pure helpers for the Streamlit review console (timeline lanes, escape, diff)."""

from __future__ import annotations

import html
from typing import Any


def escape_text(value: str) -> str:
    """HTML-escape transcript/tool text before any render path."""
    return html.escape(value, quote=True)


def timeline_lanes(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map call events into Plotly/Altair-friendly lane rows."""
    lane_for = {
        "vad": "caller_vad",
        "stt.partial": "asr",
        "stt.final": "asr",
        "endpoint": "endpoint",
        "brain.first_token": "brain",
        "brain.token": "brain",
        "tts.first_audio": "tts",
        "tts.audio": "tts",
        "playback.start": "playback",
        "playback.stop": "playback",
        "tool.call": "tools",
        "tool.result": "tools",
        "barge_in": "barge",
        "policy.denied": "policy",
    }
    rows: list[dict[str, Any]] = []
    for ev in events:
        etype = str(ev.get("type") or "")
        lane = lane_for.get(etype)
        if lane is None:
            for key, name in lane_for.items():
                if etype.startswith(key.split(".")[0]) and key in etype:
                    lane = name
                    break
        if lane is None:
            lane = "other"
        t_ms = int(ev.get("t_ms") or 0)
        rows.append(
            {
                "lane": lane,
                "type": etype,
                "t_ms": t_ms,
                "t_end_ms": t_ms + max(50, int(ev.get("duration_ms") or 200)),
                "label": escape_text(str(ev.get("payload", {}).get("text") or etype)),
            }
        )
    rows.sort(key=lambda r: (r["t_ms"], r["lane"]))
    return rows


def reference_diff(hypothesis: str, reference: str) -> list[dict[str, str]]:
    """Token-level diff for scenario reference vs ASR/agent text."""
    hyp = hypothesis.split()
    ref = reference.split()
    # LCS-based simple align
    n, m = len(hyp), len(ref)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            if hyp[i] == ref[j]:
                dp[i][j] = 1 + dp[i + 1][j + 1]
            else:
                dp[i][j] = max(dp[i + 1][j], dp[i][j + 1])
    out: list[dict[str, str]] = []
    i = j = 0
    while i < n and j < m:
        if hyp[i] == ref[j]:
            out.append({"op": "equal", "text": escape_text(hyp[i])})
            i += 1
            j += 1
        elif dp[i + 1][j] >= dp[i][j + 1]:
            out.append({"op": "insert", "text": escape_text(hyp[i])})
            i += 1
        else:
            out.append({"op": "delete", "text": escape_text(ref[j])})
            j += 1
    while i < n:
        out.append({"op": "insert", "text": escape_text(hyp[i])})
        i += 1
    while j < m:
        out.append({"op": "delete", "text": escape_text(ref[j])})
        j += 1
    return out


def scrub_tool_args(args: dict[str, Any]) -> dict[str, Any]:
    """Redact likely PII keys for review display."""
    scrubbed: dict[str, Any] = {}
    for k, v in args.items():
        key = k.lower()
        if any(p in key for p in ("phone", "email", "ssn", "address", "name")):
            scrubbed[k] = "[redacted]"
        else:
            scrubbed[k] = v
    return scrubbed
