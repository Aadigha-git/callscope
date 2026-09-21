"""TTS text normalisation for spoken delivery (design §4.2)."""

from __future__ import annotations

import re
from datetime import datetime

_DIGIT_WORDS = {
    "0": "zero",
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
}

_ONES = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
_TENS = [
    "",
    "",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
]
_MONTHS = [
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
_WEEKDAYS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

_THINK_BLOCK = re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE)
_TOOL_BLOCK = re.compile(
    r"<(?:tool|tool_call|tool_result)[^>]*>[\s\S]*?</(?:tool|tool_call|tool_result)>",
    re.IGNORECASE,
)
_TOOL_TRACE_LINE = re.compile(r"(?m)^\s*(?:Tool call|Calling tool|\[tool[^\]]*\]).*$")
_MD_BOLD = re.compile(r"\*\*([^*]+)\*\*|__([^_]+)__")
_MD_ITALIC = re.compile(r"(?<!\w)\*([^*]+)\*(?!\w)|(?<!\w)_([^_]+)_(?!\w)")
_MD_CODE = re.compile(r"`([^`]+)`")
_MD_HEADING = re.compile(r"(?m)^#{1,6}\s+")
_MD_LIST = re.compile(r"(?m)^\s*[-*+]\s+")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")

_PHONE = re.compile(r"(?<!\w)(?:\+?1[\s\-.]?)?\(?(\d{3})\)?[\s\-.]?(\d{3})[\s\-.]?(\d{4})(?!\w)")
_CODE = re.compile(
    r"(?<![A-Za-z0-9])(?=[A-Za-z0-9]*[A-Za-z])(?=[A-Za-z0-9]*\d)[A-Za-z0-9]{4,12}(?![A-Za-z0-9])"
)
_CURRENCY_RANGE = re.compile(
    r"\$\s*(\d+(?:\.\d{1,2})?)\s*(?:[-]|to)\s*\$?\s*(\d+(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
_CURRENCY = re.compile(r"\$\s*(\d+(?:\.\d{1,2})?)")
_TIME = re.compile(
    r"(?<!\d)(\d{1,2}):(\d{2})\s*(a\.?m\.?|p\.?m\.?)?(?!\d)",
    re.IGNORECASE,
)
_DATE_NAMED = re.compile(
    r"\b((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+)?"
    r"(January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+"
    r"(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(\d{4}))?\b",
    re.IGNORECASE,
)
_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DATE_US = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b")
_ORDINAL = re.compile(r"\b(\d{1,2})(st|nd|rd|th)\b", re.IGNORECASE)
_STREET_NUM = re.compile(r"(?<!\w)(\d{1,6})\s+(?=[A-Z])")


def tts_norm(text: str) -> str:
    """Normalise agent text for TTS: strip markup, speak phones/codes/dates/times."""
    if not text or not text.strip():
        return ""
    out = text
    out = _THINK_BLOCK.sub(" ", out)
    out = _TOOL_BLOCK.sub(" ", out)
    out = _TOOL_TRACE_LINE.sub(" ", out)
    out = _MD_LINK.sub(r"\1", out)
    out = _MD_BOLD.sub(lambda m: m.group(1) or m.group(2) or "", out)
    out = _MD_ITALIC.sub(lambda m: m.group(1) or m.group(2) or "", out)
    out = _MD_CODE.sub(r"\1", out)
    out = _MD_HEADING.sub("", out)
    out = _MD_LIST.sub("", out)
    out = _PHONE.sub(lambda m: _speak_phone(m.group(1), m.group(2), m.group(3)), out)
    out = _CURRENCY_RANGE.sub(
        lambda m: (
            f"between {_speak_money_amount(m.group(1))} and "
            f"{_speak_money_amount(m.group(2))} dollars"
        ),
        out,
    )
    out = _CURRENCY.sub(lambda m: f"{_speak_money_amount(m.group(1))} dollars", out)
    out = _TIME.sub(_replace_time, out)
    out = _DATE_NAMED.sub(_replace_named_date, out)
    out = _DATE_ISO.sub(_replace_iso_date, out)
    out = _DATE_US.sub(_replace_us_date, out)
    out = _ORDINAL.sub(lambda m: _speak_ordinal(int(m.group(1))), out)
    out = _CODE.sub(lambda m: _speak_code(m.group(0)), out)
    out = _STREET_NUM.sub(lambda m: _speak_street_number(m.group(1)) + " ", out)
    out = re.sub(r"[ \t]+", " ", out)
    out = re.sub(r" *\n+ *", ". ", out)
    return out.strip(" \t.,;")


def _speak_digits(digits: str) -> str:
    return " ".join(_DIGIT_WORDS[d] for d in digits if d.isdigit())


def _speak_phone(area: str, exch: str, line: str) -> str:
    return f"{_speak_digits(area)}, {_speak_digits(exch)}, {_speak_digits(line)}"


def _speak_code(code: str) -> str:
    parts: list[str] = []
    for ch in code:
        if ch.isdigit():
            parts.append(_DIGIT_WORDS[ch])
        elif ch.isalpha():
            parts.append(ch.upper())
    return " ".join(parts)


def _int_to_words(n: int) -> str:
    if n < 0:
        return "minus " + _int_to_words(-n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return _TENS[tens] if ones == 0 else f"{_TENS[tens]} {_ONES[ones]}"
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        if rest == 0:
            return f"{_ONES[hundreds]} hundred"
        return f"{_ONES[hundreds]} hundred {_int_to_words(rest)}"
    if n < 1_000_000:
        thousands, rest = divmod(n, 1000)
        head = _int_to_words(thousands) + " thousand"
        return head if rest == 0 else f"{head} {_int_to_words(rest)}"
    return " ".join(_DIGIT_WORDS[d] for d in str(n))


def _speak_money_amount(raw: str) -> str:
    if "." in raw:
        whole_s, frac_s = raw.split(".", 1)
        whole = int(whole_s or "0")
        spoken = _int_to_words(whole)
        if int(frac_s) == 0:
            return spoken
        return f"{spoken} point {_speak_digits(frac_s)}"
    return _int_to_words(int(raw))


def _speak_ordinal(n: int) -> str:
    special = {
        1: "first",
        2: "second",
        3: "third",
        4: "fourth",
        5: "fifth",
        6: "sixth",
        7: "seventh",
        8: "eighth",
        9: "ninth",
        10: "tenth",
        11: "eleventh",
        12: "twelfth",
        13: "thirteenth",
        20: "twentieth",
        21: "twenty first",
        22: "twenty second",
        23: "twenty third",
        30: "thirtieth",
        31: "thirty first",
    }
    if n in special:
        return special[n]
    base = _int_to_words(n)
    if base.endswith("y"):
        return base[:-1] + "ieth"
    return base + "th"


def _month_name(name: str) -> str:
    aliases = {
        "jan": "January",
        "feb": "February",
        "mar": "March",
        "apr": "April",
        "jun": "June",
        "jul": "July",
        "aug": "August",
        "sep": "September",
        "sept": "September",
        "oct": "October",
        "nov": "November",
        "dec": "December",
    }
    key = name.lower()
    if key in aliases:
        return aliases[key]
    return name[0].upper() + name[1:].lower()


def _speak_year(year: int) -> str:
    if year == 2000:
        return "two thousand"
    if 2001 <= year <= 2099:
        return f"two thousand {_int_to_words(year - 2000)}"
    century, rest = divmod(year, 100)
    return f"{_int_to_words(century)} {_int_to_words(rest)}" if rest else _int_to_words(century)


def _replace_named_date(m: re.Match[str]) -> str:
    weekday = (m.group(1) or "").strip().rstrip(",").strip()
    month = _month_name(m.group(2))
    day = _speak_ordinal(int(m.group(3)))
    year = m.group(4)
    if weekday and year:
        return f"{weekday}, {month} {day}, {_speak_year(int(year))}"
    if weekday:
        return f"{weekday}, {month} {day}"
    if year:
        return f"{month} {day}, {_speak_year(int(year))}"
    return f"{month} {day}"


def _replace_iso_date(m: re.Match[str]) -> str:
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        dt = datetime(y, mo, d)
    except ValueError:
        return m.group(0)
    return f"{_WEEKDAYS[dt.weekday()]}, {_MONTHS[mo]} {_speak_ordinal(d)}, {_speak_year(y)}"


def _replace_us_date(m: re.Match[str]) -> str:
    mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000
    try:
        dt = datetime(y, mo, d)
    except ValueError:
        return m.group(0)
    return f"{_WEEKDAYS[dt.weekday()]}, {_MONTHS[mo]} {_speak_ordinal(d)}, {_speak_year(y)}"


def _replace_time(m: re.Match[str]) -> str:
    hour = int(m.group(1))
    minute = int(m.group(2))
    ampm_raw = (m.group(3) or "").lower().replace(".", "")
    if not ampm_raw:
        if hour == 0:
            hour12, ampm = 12, "am"
        elif hour < 12:
            hour12, ampm = hour, "am"
        elif hour == 12:
            hour12, ampm = 12, "pm"
        else:
            hour12, ampm = hour - 12, "pm"
    else:
        hour12 = hour if 1 <= hour <= 12 else ((hour - 1) % 12) + 1
        ampm = ampm_raw
    h_words = _int_to_words(hour12)
    if minute == 0:
        spoken = h_words
    elif minute < 10:
        spoken = f"{h_words} oh {_int_to_words(minute)}"
    else:
        spoken = f"{h_words} {_int_to_words(minute)}"
    suffix = "a m" if ampm.startswith("a") else "p m"
    return f"{spoken} {suffix}"


def _speak_street_number(num: str) -> str:
    if len(num) <= 3:
        return _int_to_words(int(num))
    return _speak_digits(num)
