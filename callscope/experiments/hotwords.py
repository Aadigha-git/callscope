"""Domain hotword vocabulary for E1 (T-M5-02).

Built only from scenario population pools + Business seed catalogues — never from
frozen-test or recorded transcripts (no leakage).
"""

from __future__ import annotations

import re
from pathlib import Path

from apps.biz.store import SERVICE_TYPES, SERVICE_ZIPS
from callscope.eval.scenarios import domain_name_pool, domain_street_pool

_TOKEN_RE = re.compile(r"[A-Za-z0-9']+")


def build_hotword_list(*, max_words: int | None = None) -> list[str]:
    """Return deduped hotwords suitable for Whisper ``initial_prompt`` / ASR session."""
    words: list[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        text = " ".join(raw.split())
        if not text:
            return
        key = text.casefold()
        if key in seen:
            return
        seen.add(key)
        words.append(text)

    for name in domain_name_pool():
        _add(name)
        for part in name.replace("'", " ").split():
            if len(part) > 2:
                _add(part)
    for street in domain_street_pool():
        _add(street)
        for part in street.split():
            if part.casefold() not in {"street", "avenue", "lane", "court", "road", "boulevard"}:
                _add(part)
    for _st, display, _price, _dur in SERVICE_TYPES:
        _add(display)
        for part in display.split():
            if len(part) > 2:
                _add(part)
    for z in SERVICE_ZIPS:
        _add(z)

    if max_words is not None:
        return words[: max(0, max_words)]
    return words


def write_hotwords_file(path: Path, *, max_words: int | None = None) -> list[str]:
    words = build_hotword_list(max_words=max_words)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(words) + "\n", encoding="utf-8")
    return words


def load_hotwords_file(path: Path) -> list[str]:
    if not path.is_file():
        return []
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text and not text.startswith("#"):
            out.append(text)
    return out


def corrupt_entity_hyp(ref: str, *, seed: int = 0) -> str:
    """Deterministic ASR-like garble of NAME/ADDRESS tokens (control condition)."""
    rng_state = seed
    tokens = _TOKEN_RE.findall(ref)
    out: list[str] = []
    for tok in tokens:
        rng_state = (rng_state * 1103515245 + 12345) & 0x7FFFFFFF
        if len(tok) <= 2 or tok.isdigit():
            out.append(tok)
            continue
        if rng_state % 2 == 0:
            garb = re.sub(r"[aeiouAEIOU]", "", tok) or tok
            out.append(garb.lower())
        else:
            out.append(tok[1:] + tok[0].lower() if len(tok) > 1 else tok.lower())
    return " ".join(out)


def _consonant_skeleton(s: str) -> str:
    return "".join(c for c in s.casefold() if c.isalpha() and c not in "aeiou")


def apply_hotword_bias(hyp: str, hotwords: list[str]) -> str:
    """Restore hotword phrases when hyp tokens are near-misses (offline Whisper-bias proxy).

    Identity on already-correct text: exact casefold matches keep the original token;
    fuzzy restore only when the consonant skeleton matches a hotword token (vowel-strip
    / light garble) — never rewrites unrelated English words.
    """
    if not hotwords:
        return hyp
    tokens = hyp.split()
    if not tokens:
        return hyp
    canon: dict[str, str] = {}
    by_skel: dict[str, str] = {}
    for hw in hotwords:
        for part in hw.replace("'", " ").split():
            if len(part) < 3:
                continue
            canon.setdefault(part.casefold(), part)
            sk = _consonant_skeleton(part)
            if len(sk) >= 3:
                by_skel.setdefault(sk, part)

    fixed: list[str] = []
    for tok in tokens:
        punct_l = ""
        punct_r = ""
        core = tok
        while core and core[0] in ".,!?;:\"'(":
            punct_l += core[0]
            core = core[1:]
        while core and core[-1] in ".,!?;:\"')":
            punct_r = core[-1] + punct_r
            core = core[:-1]
        if not core:
            fixed.append(tok)
            continue
        key = core.casefold()
        if key in canon:
            fixed.append(tok)
            continue
        sk = _consonant_skeleton(core)
        surface = by_skel.get(sk) if len(sk) >= 3 else None
        if surface is not None:
            key_vowels = sum(1 for c in key if c in "aeiou")
            surf_vowels = sum(1 for c in surface.casefold() if c in "aeiou")
            # Vowel-stripped garbles may shrink by ~vowel count; otherwise tight.
            allow_gap = surf_vowels if key_vowels == 0 else 1
            if abs(len(key) - len(surface)) > allow_gap:
                surface = None
        if surface is None and len(key) >= 4:
            # Rotation garble: "aplem" ← "maple"
            for i in range(1, len(key)):
                rot = key[i:] + key[:i]
                if rot in canon:
                    surface = canon[rot]
                    break
        if surface is not None and surface.casefold() != key:
            fixed.append(f"{punct_l}{surface}{punct_r}")
        else:
            fixed.append(tok)

    return " ".join(fixed)


__all__ = [
    "apply_hotword_bias",
    "build_hotword_list",
    "corrupt_entity_hyp",
    "load_hotwords_file",
    "write_hotwords_file",
]
