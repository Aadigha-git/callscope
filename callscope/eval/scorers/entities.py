"""Entity extractors and scorers (PHONE, DATE, TIME, NAME, ADDRESS, CODE)."""

from __future__ import annotations

import re
from collections.abc import Iterable

from callscope.eval.normalize import normalize
from callscope.eval.types import EntityScore

_CODE_RE = re.compile(r"\b(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]{6,12}\b", re.IGNORECASE)
_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_MD_DATE_RE = re.compile(r"\b(\d{2}-\d{2})(?:-\d{4})?\b")
_TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
_ADDR_RE = re.compile(
    r"\b(\d{1,5})\s+([A-Za-z][A-Za-z]*(?:\s+[A-Za-z][A-Za-z]*){0,3})\s+"
    r"(street|st|avenue|ave|road|rd|lane|ln|court|ct|boulevard|blvd|drive|dr)\b",
    re.IGNORECASE,
)


def _digits_only(s: str) -> str:
    return re.sub(r"\D", "", s)


def soundex(name: str) -> str:
    """American Soundex for phonetic-match flag (NAME)."""
    s = re.sub(r"[^A-Za-z]", "", name).upper()
    if not s:
        return ""
    first = s[0]
    mapping = str.maketrans("BFPVCGJKQSXZDTLMNR", "111122222222334556")
    coded = s[1:].translate(mapping)
    coded = re.sub(r"(\d)\1+", r"\1", coded)
    coded = re.sub(r"[AEIOUYHW]", "", coded)
    return (first + coded + "000")[:4]


def extract_phones(text: str) -> list[str]:
    norm = normalize(text)
    found = list(dict.fromkeys(re.findall(r"\d{10}", norm)))
    digits = _digits_only(norm)
    if len(digits) == 10 and digits not in found:
        found.append(digits)
    return found


def extract_dates(text: str) -> list[str]:
    norm = normalize(text)
    return list(dict.fromkeys(_ISO_DATE_RE.findall(norm) + _MD_DATE_RE.findall(norm)))


def extract_times(text: str) -> list[str]:
    norm = normalize(text)
    return [f"{h}:{m}" for h, m in _TIME_RE.findall(norm)]


def extract_codes(text: str) -> list[str]:
    return [m.group(0).upper() for m in _CODE_RE.finditer(text)]


def extract_addresses(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for m in _ADDR_RE.finditer(text):
        num = m.group(1)
        street = normalize(m.group(2) + " " + m.group(3))
        out.append((num, street))
    return out


def token_f1(ref: str, hyp: str) -> float:
    r = set(normalize(ref).split())
    h = set(normalize(hyp).split())
    if not r and not h:
        return 1.0
    if not r or not h:
        return 0.0
    inter = len(r & h)
    precision = inter / len(h)
    recall = inter / len(r)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def phone_partial(ref_digits: str, hyp_digits: str) -> float:
    """Fraction of reference digits matched in order (partial credit)."""
    ref = _digits_only(ref_digits)
    hyp = _digits_only(hyp_digits)
    if not ref:
        return 1.0 if not hyp else 0.0
    if not hyp:
        return 0.0
    n, m = len(ref), len(hyp)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref[i - 1] == hyp[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[n][m] / n


def score_phone(ref: str, hyp: str) -> EntityScore:
    rd, hd = _digits_only(ref), _digits_only(hyp)
    exact = rd == hd and bool(rd)
    partial = phone_partial(rd, hd)
    return EntityScore(
        entity_type="PHONE",
        ref=rd,
        hyp=hd,
        exact=exact,
        score=1.0 if exact else partial,
        partial=partial,
    )


def score_date(ref: str, hyp: str) -> EntityScore:
    rn = normalize(ref)
    hn = normalize(hyp)
    refs = extract_dates(rn) or [rn]
    hyps = extract_dates(hn) or [hn]
    exact = refs[0] == hyps[0]
    return EntityScore(
        entity_type="DATE",
        ref=refs[0],
        hyp=hyps[0],
        exact=exact,
        score=1.0 if exact else 0.0,
    )


def score_time(ref: str, hyp: str) -> EntityScore:
    rn, hn = normalize(ref), normalize(hyp)
    refs = extract_times(rn) or [rn]
    hyps = extract_times(hn) or [hn]
    exact = refs[0] == hyps[0]
    return EntityScore(
        entity_type="TIME",
        ref=refs[0],
        hyp=hyps[0],
        exact=exact,
        score=1.0 if exact else 0.0,
    )


def score_name(ref: str, hyp: str) -> EntityScore:
    f1 = token_f1(ref, hyp)
    phonetic = soundex(ref) == soundex(hyp) and bool(soundex(ref))
    exact = normalize(ref) == normalize(hyp) and bool(normalize(ref))
    return EntityScore(
        entity_type="NAME",
        ref=ref,
        hyp=hyp,
        exact=exact,
        score=f1,
        phonetic_match=phonetic,
    )


def score_address(ref: str, hyp: str) -> EntityScore:
    ra = extract_addresses(ref)
    ha = extract_addresses(hyp)
    if ra and ha:
        exact = ra[0][0] == ha[0][0] and ra[0][1] == ha[0][1]
        num_ok = ra[0][0] == ha[0][0]
        street_ok = ra[0][1] == ha[0][1]
        score = (1.0 if num_ok else 0.0) * 0.5 + (1.0 if street_ok else 0.0) * 0.5
        return EntityScore(
            entity_type="ADDRESS",
            ref=f"{ra[0][0]} {ra[0][1]}",
            hyp=f"{ha[0][0]} {ha[0][1]}",
            exact=exact,
            score=score,
        )
    f1 = token_f1(ref, hyp)
    return EntityScore(
        entity_type="ADDRESS",
        ref=ref,
        hyp=hyp,
        exact=normalize(ref) == normalize(hyp),
        score=f1,
    )


def score_code(ref: str, hyp: str) -> EntityScore:
    r = ref.strip().upper()
    h = hyp.strip().upper()
    exact = r == h and bool(r)
    return EntityScore(
        entity_type="CODE",
        ref=r,
        hyp=h,
        exact=exact,
        score=1.0 if exact else 0.0,
    )


_SCORERS = {
    "PHONE": score_phone,
    "DATE": score_date,
    "TIME": score_time,
    "NAME": score_name,
    "ADDRESS": score_address,
    "CODE": score_code,
}


def score_entity(entity_type: str, ref: str, hyp: str) -> EntityScore:
    key = entity_type.upper()
    if key not in _SCORERS:
        raise ValueError(f"unknown entity type {entity_type!r}")
    return _SCORERS[key](ref, hyp)


def score_entities(
    pairs: Iterable[tuple[str, str, str]],
) -> list[EntityScore]:
    """Score ``(entity_type, ref, hyp)`` triples."""
    return [score_entity(t, r, h) for t, r, h in pairs]


__all__ = [
    "extract_addresses",
    "extract_codes",
    "extract_dates",
    "extract_phones",
    "extract_times",
    "phone_partial",
    "score_address",
    "score_code",
    "score_date",
    "score_entities",
    "score_entity",
    "score_name",
    "score_phone",
    "score_time",
    "soundex",
    "token_f1",
]
