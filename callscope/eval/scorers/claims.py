"""Rule-based factual claim extraction and KB/tool support checks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

ClaimKind = Literal[
    "price",
    "hours",
    "service_area",
    "policy",
    "availability",
    "other",
]

# Patterns that often indicate a factual claim worth checking.
_CLAIM_PATTERNS: list[tuple[ClaimKind, re.Pattern[str]]] = [
    ("price", re.compile(r"\$\s?\d+|costs?\s+\d+|price(?:d|s)?\s+(?:is|of)|only\s+\$?", re.I)),
    ("hours", re.compile(r"open\s+(?:from|until)|hours?\s+are|we\s+(?:open|close)\s+at", re.I)),
    (
        "service_area",
        re.compile(
            r"serve(?:s|d)?\s+(?:only\s+)?[\w\s]+|within\s+\d+\s+miles|service\s+area",
            re.I,
        ),
    ),
    ("policy", re.compile(r"policy|cancellation\s+fee|must\s+(?:pay|provide)|required\s+to", re.I)),
    (
        "availability",
        re.compile(
            r"available\s+(?:on|at|tomorrow|today)|next\s+(?:slot|opening)|booked\s+solid",
            re.I,
        ),
    ),
]

# Gap topics from docs/kb_gaps.md — treating these as unsupported unless in evidence.
_GAP_HINTS: dict[str, re.Pattern[str]] = {
    "price_specific": re.compile(
        r"exactly\s+\$\d+|costs?\s+exactly|capacitor\s+replacement\s+costs", re.I
    ),
    "weekend_surcharge": re.compile(
        r"weekend\s+surcharge|after[- ]hours\s+(?:fee|surcharge)\s+\$",
        re.I,
    ),
    "part_sku": re.compile(r"\bSKU\b|part\s+number\s+[A-Z0-9-]+|OEM\s+#", re.I),
    "eta_minutes": re.compile(r"arrive(?:s|ing)?\s+in\s+\d+\s+minutes|guaranteed\s+ETA", re.I),
    "competitor": re.compile(r"cheaper\s+than\s+\w+|competitor", re.I),
    "legal": re.compile(r"ordinance\s+number|legal\s+advice|permit\s+fee\s+is\s+\$", re.I),
    "medical": re.compile(r"mold\s+is\s+safe|medical\s+advice|gas\s+exposure\s+is\s+fine", re.I),
    "other_customers": re.compile(
        r"another\s+customer|other\s+customer(?:'s)?\s+(?:phone|address|appointment)", re.I
    ),
}


@dataclass(frozen=True, slots=True)
class Claim:
    text: str
    kind: ClaimKind
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class ClaimCheck:
    claim: Claim
    supported: bool
    reason: str
    gap_id: str | None = None


@dataclass(slots=True)
class ClaimsResult:
    claims: list[Claim] = field(default_factory=list)
    checks: list[ClaimCheck] = field(default_factory=list)

    @property
    def unsupported_count(self) -> int:
        return sum(1 for c in self.checks if not c.supported)

    @property
    def hallucination_rate(self) -> float:
        if not self.checks:
            return 0.0
        return self.unsupported_count / len(self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_claims": len(self.claims),
            "unsupported_count": self.unsupported_count,
            "hallucination_rate": self.hallucination_rate,
            "checks": [
                {
                    "text": c.claim.text,
                    "kind": c.claim.kind,
                    "supported": c.supported,
                    "reason": c.reason,
                    "gap_id": c.gap_id,
                }
                for c in self.checks
            ],
        }


def extract_claims(utterance: str) -> list[Claim]:
    """Extract candidate factual spans from an agent utterance."""
    found: list[Claim] = []
    for kind, pat in _CLAIM_PATTERNS:
        for m in pat.finditer(utterance):
            # Expand to sentence-ish window
            start = max(0, utterance.rfind(".", 0, m.start()) + 1)
            end = utterance.find(".", m.end())
            if end < 0:
                end = len(utterance)
            else:
                end += 1
            span = utterance[start:end].strip()
            if span:
                found.append(Claim(text=span, kind=kind, start=start, end=end))
    # Dedupe overlapping identical text
    uniq: list[Claim] = []
    seen: set[str] = set()
    for c in found:
        key = c.text.lower()
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    return uniq


def _evidence_blob(kb_docs: list[str], tool_results: list[dict[str, Any]]) -> str:
    parts = list(kb_docs)
    for tr in tool_results:
        parts.append(str(tr.get("name") or ""))
        parts.append(str(tr.get("result") or tr.get("output") or ""))
        args = tr.get("args") or tr.get("arguments") or {}
        if isinstance(args, dict):
            parts.extend(f"{k}={v}" for k, v in args.items())
    return "\n".join(parts).lower()


def check_claim_support(
    claim: Claim,
    *,
    kb_docs: list[str],
    tool_results: list[dict[str, Any]] | None = None,
    must_not_claim: list[str] | None = None,
) -> ClaimCheck:
    """Return whether ``claim`` is supported by KB text / tool results / gap rules."""
    text_l = claim.text.lower()
    evidence = _evidence_blob(kb_docs, tool_results or [])
    forbidden = {t.lower() for t in (must_not_claim or [])}

    for gap_id, pat in _GAP_HINTS.items():
        if pat.search(claim.text):
            return ClaimCheck(
                claim=claim,
                supported=False,
                reason=f"matches KB gap pattern {gap_id}",
                gap_id=gap_id,
            )

    # Scenario-declared forbidden topics on price-like claims
    if claim.kind == "price" and "price_specific" in forbidden:
        return ClaimCheck(
            claim=claim,
            supported=False,
            reason="must_not_claim includes price_specific",
            gap_id="price_specific",
        )

    # Token overlap heuristic against evidence
    tokens = [t for t in re.findall(r"[a-z0-9$]+", text_l) if len(t) > 2]
    if not tokens:
        return ClaimCheck(claim=claim, supported=True, reason="no contentful tokens")
    hits = sum(1 for t in tokens if t in evidence)
    ratio = hits / len(tokens)
    if evidence and ratio >= 0.4:
        return ClaimCheck(claim=claim, supported=True, reason=f"evidence overlap {ratio:.2f}")
    if not evidence:
        return ClaimCheck(
            claim=claim,
            supported=False,
            reason="no KB/tool evidence provided",
        )
    return ClaimCheck(claim=claim, supported=False, reason=f"weak evidence overlap {ratio:.2f}")


def score_claims(
    utterance: str,
    *,
    kb_docs: list[str] | None = None,
    tool_results: list[dict[str, Any]] | None = None,
    must_not_claim: list[str] | None = None,
) -> ClaimsResult:
    claims = extract_claims(utterance)
    checks = [
        check_claim_support(
            c,
            kb_docs=kb_docs or [],
            tool_results=tool_results,
            must_not_claim=must_not_claim,
        )
        for c in claims
    ]
    return ClaimsResult(claims=claims, checks=checks)


__all__ = [
    "Claim",
    "ClaimCheck",
    "ClaimsResult",
    "check_claim_support",
    "extract_claims",
    "score_claims",
]
