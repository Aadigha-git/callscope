"""Shared ASR/eval text normaliser (design §4.6). Versioned for metric comparability."""

from __future__ import annotations

import re

NORMALIZER_VERSION = "1.0.0"

_FILLERS = frozenset(
    {
        "um",
        "uh",
        "er",
        "ah",
        "eh",
        "hmm",
        "hm",
        "like",
        "youknow",
        "you_know",
    }
)

_ONES = {
    "zero": "0",
    "oh": "0",
    "o": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
}

_TEENS = {
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
}

_TENS = {
    "twenty": "20",
    "thirty": "30",
    "forty": "40",
    "fifty": "50",
    "sixty": "60",
    "seventy": "70",
    "eighty": "80",
    "ninety": "90",
}

_ORDINALS = {
    "first": "1",
    "second": "2",
    "third": "3",
    "fourth": "4",
    "fifth": "5",
    "sixth": "6",
    "seventh": "7",
    "eighth": "8",
    "ninth": "9",
    "tenth": "10",
    "eleventh": "11",
    "twelfth": "12",
    "thirteenth": "13",
    "fourteenth": "14",
    "fifteenth": "15",
    "sixteenth": "16",
    "seventeenth": "17",
    "eighteenth": "18",
    "nineteenth": "19",
    "twentieth": "20",
    "thirtieth": "30",
}

_MONTHS = {
    "january": "01",
    "jan": "01",
    "february": "02",
    "feb": "02",
    "march": "03",
    "mar": "03",
    "april": "04",
    "apr": "04",
    "may": "05",
    "june": "06",
    "jun": "06",
    "july": "07",
    "jul": "07",
    "august": "08",
    "aug": "08",
    "september": "09",
    "sep": "09",
    "sept": "09",
    "october": "10",
    "oct": "10",
    "november": "11",
    "nov": "11",
    "december": "12",
    "dec": "12",
}

_DIGIT_TO_WORD = {v: k for k, v in _ONES.items() if k not in {"oh", "o"}}

_PUNCT = re.compile(r"[^\w\s]|_")
_MULTI_SPACE = re.compile(r"\s+")
_YOU_KNOW = re.compile(r"\byou\s+know\b")
_DATE_TOKEN = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_MD_TOKEN = re.compile(r"\b(\d{2})-(\d{2})\b")
_TIME_TOKEN = re.compile(r"\b(\d{2}):(\d{2})\b")
_PROTECTED_DATE = re.compile(r"\b(\d{4})D(\d{2})D(\d{2})\b")
_PROTECTED_MD = re.compile(r"\b(\d{2})D(\d{2})\b")
_PROTECTED_TIME = re.compile(r"\b(\d{2})T(\d{2})\b")
_DOUBLE_TRIPLE = re.compile(
    r"\b(double|triple)\s+(zero|oh|o|one|two|three|four|five|six|seven|eight|nine|\d)\b"
)
_PHONE_GROUPED = re.compile(
    r"(?<!\d)(?:\+?1[\s\-.]?)?\(?(\d{3})\)?[\s\-.]?(\d{3})[\s\-.]?(\d{4})(?!\d)"
)
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_US_DATE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b")
_MONTH_DAY = re.compile(
    r"\b(" + "|".join(_MONTHS) + r")\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*,?\s*(\d{2,4}))?\b",
    re.IGNORECASE,
)
_TIME = re.compile(
    r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?\b",
    re.IGNORECASE,
)
_COMPOUND_TENS = re.compile(
    r"\b(twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)[\s-](one|two|three|four|five|six|seven|eight|nine)\b",
    re.IGNORECASE,
)
_STANDALONE_NUMBER_WORD = re.compile(
    r"\b("
    + "|".join(
        sorted(
            list(_TEENS) + list(_TENS) + list(_ONES) + list(_ORDINALS),
            key=len,
            reverse=True,
        )
    )
    + r")\b",
    re.IGNORECASE,
)


def digits_to_words(text: str) -> str:
    """Expand digit runs to spoken words (inverse helper for golden tests)."""

    def repl(match: re.Match[str]) -> str:
        return " ".join(_DIGIT_TO_WORD.get(ch, ch) for ch in match.group(0))

    return re.sub(r"\d+", repl, text)


def _expand_double_triple(match: re.Match[str]) -> str:
    kind = match.group(1).lower()
    token = match.group(2).lower()
    digit = _ONES.get(token, token)  # token is digit or ones-word per regex
    n = 2 if kind == "double" else 3
    return (" " + digit) * n


def _compound_tens(match: re.Match[str]) -> str:
    tens = int(_TENS[match.group(1).lower()])
    ones = int(_ONES[match.group(2).lower()])
    return str(tens + ones)


def _number_word(match: re.Match[str]) -> str:
    w = match.group(1).lower()
    if w in _ORDINALS:
        return _ORDINALS[w]
    if w in _TEENS:
        return _TEENS[w]
    if w in _TENS:
        return _TENS[w]
    return _ONES[w]


def _month_day(match: re.Match[str]) -> str:
    month = _MONTHS[match.group(1).lower()]
    day = int(match.group(2))
    year = match.group(3)
    if year:
        y = int(year)
        if y < 100:
            y += 2000
        return f"{y:04d}-{month}-{day:02d}"
    return f"{month}-{day:02d}"


def _us_date(match: re.Match[str]) -> str:
    a, b, y = match.group(1), match.group(2), match.group(3)
    month, day = int(a), int(b)
    if y:
        year = int(y)
        if year < 100:
            year += 2000
        return f"{year:04d}-{month:02d}-{day:02d}"
    return f"{month:02d}-{day:02d}"


def _time(match: re.Match[str]) -> str:
    hour = int(match.group(1))
    minute = match.group(2) or "00"
    meridiem = match.group(3)
    if meridiem:
        m = meridiem.lower().replace(".", "")
        if m.startswith("p") and hour < 12:
            hour += 12
        if m.startswith("a") and hour == 12:
            hour = 0
        return f"{hour:02d}:{minute}"
    if match.group(2) is not None:
        return f"{hour:02d}:{minute}"
    # bare small integers stay as numbers via other paths; leave clock-like alone
    return match.group(0)


def normalize_phone_digits(text: str) -> str:
    """Collapse spoken/grouped US phones to contiguous 10-digit sequences where possible."""

    def repl(match: re.Match[str]) -> str:
        return match.group(1) + match.group(2) + match.group(3)

    return _PHONE_GROUPED.sub(repl, text)


def normalize(text: str, *, emails_as_words: bool = False) -> str:
    """Lowercase, strip fillers/punct, normalise numbers/dates/phones for ASR scoring."""
    del emails_as_words  # reserved for future; keeps signature stable
    if not text:
        return ""
    s = text.casefold()
    s = s.replace("'", "")
    s = _YOU_KNOW.sub(" ", s)
    s = _DOUBLE_TRIPLE.sub(_expand_double_triple, s)
    s = _COMPOUND_TENS.sub(_compound_tens, s)
    s = _MONTH_DAY.sub(_month_day, s)
    s = _ISO_DATE.sub(lambda m: f"{m.group(1)}-{m.group(2)}-{m.group(3)}", s)
    s = _US_DATE.sub(_us_date, s)
    s = _TIME.sub(_time, s)
    s = _STANDALONE_NUMBER_WORD.sub(_number_word, s)
    s = normalize_phone_digits(s)
    # Protect structured tokens from punctuation stripping.
    s = _DATE_TOKEN.sub(r"\1D\2D\3", s)
    s = _MD_TOKEN.sub(r"\1D\2", s)
    s = _TIME_TOKEN.sub(r"\1T\2", s)
    s = _PUNCT.sub(" ", s)
    s = _PROTECTED_DATE.sub(r"\1-\2-\3", s)
    s = _PROTECTED_MD.sub(r"\1-\2", s)
    s = _PROTECTED_TIME.sub(r"\1:\2", s)
    tokens = []
    for tok in s.split():
        if tok in _FILLERS or tok == "youknow":
            continue
        tokens.append(tok)
    s = " ".join(tokens)
    return _MULTI_SPACE.sub(" ", s).strip()


__all__ = [
    "NORMALIZER_VERSION",
    "digits_to_words",
    "normalize",
    "normalize_phone_digits",
]
