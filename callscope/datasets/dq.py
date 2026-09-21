"""Data-quality checks for synthetic/recorded datasets (design 4.6)."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np

from callscope.datasets.io_audio import SAMPLE_RATE_HZ, peak, read_wav

Severity = Literal["error", "warn", "info"]

# Bounds tuned for short synthetic caller clips and telephony C0-C5.
MIN_DURATION_S = 0.2
MAX_DURATION_S = 120.0
MAX_CLIP_FRAC = 0.01
MAX_SILENCE_FRAC = 0.85
MIN_CHARS_PER_SEC = 0.5
MAX_CHARS_PER_SEC = 40.0
LOUDNESS_RMS_DBFS_MIN = -50.0
LOUDNESS_RMS_DBFS_MAX = -1.0


@dataclass(frozen=True, slots=True)
class Finding:
    check: str
    severity: Severity
    message: str
    item_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DqReport:
    findings: list[Finding] = field(default_factory=list)
    n_items: int = 0
    slice_counts: dict[str, int] = field(default_factory=dict)

    @property
    def dq_passed(self) -> bool:
        return not any(f.severity == "error" for f in self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dq_passed": self.dq_passed,
            "n_items": self.n_items,
            "slice_counts": dict(self.slice_counts),
            "findings": [f.to_dict() for f in self.findings],
        }


def _rms_dbfs(audio: np.ndarray[Any, Any]) -> float:
    rms = float(np.sqrt(np.mean(np.square(audio.astype(np.float64))) + 1e-12))
    return float(20.0 * np.log10(rms + 1e-12))


def _silence_frac(audio: np.ndarray[Any, Any], thresh: float = 0.01) -> float:
    if audio.size == 0:
        return 1.0
    return float(np.mean(np.abs(audio) < thresh))


def _clip_frac(audio: np.ndarray[Any, Any], level: float = 0.99) -> float:
    if audio.size == 0:
        return 0.0
    return float(np.mean(np.abs(audio) >= level))


def check_format_sample_rate(
    item: dict[str, Any],
    audio: np.ndarray[Any, Any],
    sr: int,
) -> list[Finding]:
    out: list[Finding] = []
    iid = str(item.get("item_id", ""))
    if sr != SAMPLE_RATE_HZ:
        out.append(
            Finding(
                "format_sample_rate",
                "error",
                f"sample rate {sr} != {SAMPLE_RATE_HZ}",
                iid,
            )
        )
    if audio.ndim != 1:
        out.append(Finding("format_sample_rate", "error", "audio must be mono", iid))
    return out


def check_duration(item: dict[str, Any], audio: np.ndarray[Any, Any], sr: int) -> list[Finding]:
    iid = str(item.get("item_id", ""))
    dur = len(audio) / float(sr) if sr else 0.0
    if dur < MIN_DURATION_S or dur > MAX_DURATION_S:
        return [
            Finding(
                "duration_bounds",
                "error",
                f"duration {dur:.3f}s outside [{MIN_DURATION_S},{MAX_DURATION_S}]",
                iid,
            )
        ]
    return []


def check_clipping(item: dict[str, Any], audio: np.ndarray[Any, Any]) -> list[Finding]:
    iid = str(item.get("item_id", ""))
    frac = _clip_frac(audio)
    if frac > MAX_CLIP_FRAC or peak(audio) >= 1.0:
        return [
            Finding(
                "clipping",
                "error",
                f"clipping frac={frac:.4f} peak={peak(audio):.3f}",
                iid,
            )
        ]
    return []


def check_silence(item: dict[str, Any], audio: np.ndarray[Any, Any]) -> list[Finding]:
    iid = str(item.get("item_id", ""))
    frac = _silence_frac(audio)
    if frac > MAX_SILENCE_FRAC:
        return [Finding("silence_ratio", "error", f"silence frac={frac:.3f}", iid)]
    return []


def check_loudness(item: dict[str, Any], audio: np.ndarray[Any, Any]) -> list[Finding]:
    """RMS dBFS proxy for LUFS (true LUFS deferred; same gate intent)."""
    iid = str(item.get("item_id", ""))
    db = _rms_dbfs(audio)
    if db < LOUDNESS_RMS_DBFS_MIN or db > LOUDNESS_RMS_DBFS_MAX:
        return [
            Finding(
                "loudness",
                "error",
                f"rms_dbfs={db:.1f} outside [{LOUDNESS_RMS_DBFS_MIN},{LOUDNESS_RMS_DBFS_MAX}]",
                iid,
            )
        ]
    return []


def check_transcript_rate(
    item: dict[str, Any],
    audio: np.ndarray[Any, Any],
    sr: int,
) -> list[Finding]:
    iid = str(item.get("item_id", ""))
    text = str(item.get("text") or item.get("ref_transcript") or "")
    dur = len(audio) / float(sr) if sr else 0.0
    if dur <= 0:
        return [Finding("transcript_rate", "error", "zero duration", iid)]
    rate = len(text) / dur
    if rate < MIN_CHARS_PER_SEC or rate > MAX_CHARS_PER_SEC:
        return [
            Finding(
                "transcript_rate",
                "error",
                f"chars/sec={rate:.2f} outside [{MIN_CHARS_PER_SEC},{MAX_CHARS_PER_SEC}]",
                iid,
            )
        ]
    return []


def check_label_completeness(item: dict[str, Any]) -> list[Finding]:
    iid = str(item.get("item_id", ""))
    required = ("item_id", "scenario_id", "voice", "condition", "audio_sha256", "text")
    missing = [k for k in required if not item.get(k) and item.get(k) != 0]
    if missing:
        return [Finding("label_completeness", "error", f"missing fields: {missing}", iid)]
    return []


def check_slot_consistency(
    item: dict[str, Any],
    scenario_slots: dict[str, Any] | None,
) -> list[Finding]:
    """If expanded slots present, values must appear in transcript text when templated."""
    iid = str(item.get("item_id", ""))
    slots = scenario_slots or item.get("slots") or {}
    if not isinstance(slots, dict) or not slots:
        return []
    text = str(item.get("text") or "")
    out: list[Finding] = []
    for key, val in slots.items():
        if key in {"service_type", "topic", "reason", "preferred_date", "alternative_date"}:
            continue
        s = str(val)
        if s and s not in text and "{{" not in s:
            # Soft: warn when a concrete slot value is absent (synthetic beeps may omit)
            out.append(
                Finding(
                    "slot_consistency",
                    "warn",
                    f"slot {key}={s!r} not found in transcript",
                    iid,
                )
            )
    return out


def check_duplicate_hashes(items: list[dict[str, Any]]) -> list[Finding]:
    counts: Counter[str] = Counter(str(i.get("audio_sha256", "")) for i in items)
    out: list[Finding] = []
    for digest, n in counts.items():
        if not digest or n < 2:
            continue
        for item in items:
            if item.get("audio_sha256") == digest:
                out.append(
                    Finding(
                        "duplicate_hash",
                        "error",
                        f"duplicate audio_sha256 {digest[:12]}… (n={n})",
                        str(item.get("item_id", "")),
                    )
                )
    return out


def check_split_leakage(items: list[dict[str, Any]]) -> list[Finding]:
    """A voice or scenario-variant must not appear in more than one split."""
    voice_splits: dict[str, set[str]] = {}
    variant_splits: dict[str, set[str]] = {}
    for item in items:
        split = str(item.get("split") or "")
        if not split:
            continue
        voice = str(item.get("voice") or "")
        variant = f"{item.get('scenario_id')}:{item.get('variant')}"
        if voice:
            voice_splits.setdefault(voice, set()).add(split)
        variant_splits.setdefault(variant, set()).add(split)
    out: list[Finding] = []
    for voice, splits in voice_splits.items():
        if len(splits) > 1:
            out.append(
                Finding(
                    "split_leakage",
                    "error",
                    f"voice {voice!r} leaks across splits {sorted(splits)}",
                    None,
                )
            )
    for variant, splits in variant_splits.items():
        if len(splits) > 1:
            out.append(
                Finding(
                    "split_leakage",
                    "error",
                    f"variant {variant!r} leaks across splits {sorted(splits)}",
                    None,
                )
            )
    return out


def slice_balance_report(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for item in items:
        cond = item.get("condition", "unknown")
        voice = item.get("voice", "unknown")
        split = item.get("split", "unassigned")
        counts[f"cond={cond}"] += 1
        counts[f"voice={voice}"] += 1
        counts[f"split={split}"] += 1
    return dict(sorted(counts.items()))


def run_dq(
    items: list[dict[str, Any]],
    *,
    audio_root: Path,
    check_audio: bool = True,
) -> DqReport:
    """Run all DQ checks. Any ``error`` finding => ``dq_passed=false``."""
    report = DqReport(n_items=len(items), slice_counts=slice_balance_report(items))
    report.findings.extend(check_duplicate_hashes(items))
    report.findings.extend(check_split_leakage(items))

    for item in items:
        report.findings.extend(check_label_completeness(item))
        report.findings.extend(check_slot_consistency(item, None))
        if not check_audio:
            continue
        rel = item.get("wav_relpath") or item.get("audio_uri")
        if not rel:
            report.findings.append(
                Finding(
                    "format_sample_rate",
                    "error",
                    "missing wav_relpath/audio_uri",
                    str(item.get("item_id", "")),
                )
            )
            continue
        path = audio_root / str(rel)
        if not path.is_file():
            # allow paths already absolute under audio_root/audio/
            alt = audio_root / "audio" / Path(str(rel)).name
            path = alt if alt.is_file() else path
        if not path.is_file():
            report.findings.append(
                Finding(
                    "format_sample_rate",
                    "error",
                    f"missing audio file {rel}",
                    str(item.get("item_id", "")),
                )
            )
            continue
        audio, sr = read_wav(path)
        report.findings.extend(check_format_sample_rate(item, audio, sr))
        report.findings.extend(check_duration(item, audio, sr))
        report.findings.extend(check_clipping(item, audio))
        report.findings.extend(check_silence(item, audio))
        report.findings.extend(check_loudness(item, audio))
        report.findings.extend(check_transcript_rate(item, audio, sr))

    # Balance as info finding
    report.findings.append(
        Finding(
            "slice_balance",
            "info",
            f"slice counts: {report.slice_counts}",
            None,
        )
    )
    return report


__all__ = [
    "DqReport",
    "Finding",
    "check_clipping",
    "check_duplicate_hashes",
    "check_duration",
    "check_format_sample_rate",
    "check_label_completeness",
    "check_loudness",
    "check_silence",
    "check_slot_consistency",
    "check_split_leakage",
    "check_transcript_rate",
    "run_dq",
    "slice_balance_report",
]
