"""Scenario schema, YAML loading, and deterministic template expansion (T-M3-01)."""

from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta
from pathlib import Path
from random import Random
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

# Short claim keys used in scenario YAML → Gap IDs in docs/kb_gaps.md
MUST_NOT_CLAIM_TO_GAP: dict[str, str] = {
    "price_specific": "GAP-PRICE-EXACT",
    "weekend_surcharge": "GAP-WEEKEND-SURCHARGE",
    "part_sku": "GAP-PART-SKU",
    "eta_minutes": "GAP-ETA-MINUTES",
    "competitor": "GAP-COMPETITOR",
    "legal": "GAP-LEGAL",
    "medical": "GAP-MEDICAL",
    "other_customers": "GAP-OTHER-CUSTOMERS",
}

_HARD_NAMES: tuple[str, ...] = (
    "Siobhan O'Neill",
    "Nguyen Tran",
    "Xavier Quintero",
    "Aoife Brennan",
    "Joaquin Reyes",
    "Beatrice Mbeki",
)

_STREETS: tuple[str, ...] = (
    "Maple Street",
    "Oak Avenue",
    "Cedar Lane",
    "Pine Court",
    "Willow Road",
    "Birch Boulevard",
)

_TEMPLATE_RE = re.compile(r"\{\{(\w+)\}\}")


class ScenarioTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    caller: str
    pause_ms: int | None = Field(default=None, ge=0)
    barge_in_at_ms: int | None = Field(default=None, ge=0)


class ExpectedToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class ScenarioExpected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_calls: list[ExpectedToolCall] = Field(default_factory=list)
    final_state: dict[str, Any] = Field(default_factory=dict)
    must_confirm_before_mutation: bool = False
    must_not_claim: list[str] = Field(default_factory=list)

    @field_validator("must_not_claim")
    @classmethod
    def _known_claim_keys(cls, values: list[str]) -> list[str]:
        for key in values:
            if key not in MUST_NOT_CLAIM_TO_GAP and not key.startswith("GAP-"):
                known = ", ".join(sorted(MUST_NOT_CLAIM_TO_GAP))
                raise ValueError(f"unknown must_not_claim {key!r}; use GAP-* or one of: {known}")
        return values


class Scenario(BaseModel):
    """One scenario template (design §4.6)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    intent: str
    slots: dict[str, Any] = Field(default_factory=dict)
    turns: list[ScenarioTurn]
    expected: ScenarioExpected = Field(default_factory=ScenarioExpected)
    tags: list[str] = Field(default_factory=list)
    kb_gaps: list[str] = Field(default_factory=list)
    adversarial: bool = False


class ExpandedScenario(BaseModel):
    """Scenario after template substitution for a (seed, variant)."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    seed: int
    variant: int
    intent: str
    slots: dict[str, Any]
    turns: list[ScenarioTurn]
    expected: ScenarioExpected
    tags: list[str]
    kb_gaps: list[str]
    adversarial: bool
    bindings: dict[str, str]


def scenarios_dir() -> Path:
    """Repo ``eval/scenarios`` directory (next to this package via parents)."""
    # callscope/eval/scenarios.py → repo root is parents[2]
    return Path(__file__).resolve().parents[2] / "eval" / "scenarios"


def kb_gaps_path() -> Path:
    return Path(__file__).resolve().parents[2] / "docs" / "kb_gaps.md"


def load_kb_gap_ids(path: Path | None = None) -> set[str]:
    text = (path or kb_gaps_path()).read_text(encoding="utf-8")
    return set(re.findall(r"\bGAP-[A-Z0-9-]+\b", text))


def load_scenario(path: Path) -> Scenario:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected mapping")
    return Scenario.model_validate(data)


def load_all_scenarios(directory: Path | None = None) -> list[Scenario]:
    root = directory or scenarios_dir()
    paths = sorted(root.glob("*.yaml"))
    if not paths:
        raise FileNotFoundError(f"no scenario YAML files in {root}")
    return [load_scenario(p) for p in paths]


def _rng_for(scenario_id: str, seed: int, variant: int) -> Random:
    material = f"{scenario_id}:{seed}:{variant}".encode()
    digest = hashlib.sha256(material).hexdigest()
    # Deterministic fixture RNG only — not for secrets.
    return Random(int(digest[:16], 16))  # noqa: S311


def _next_weekday(as_of: date, weekday: int) -> date:
    """Next calendar day with ``weekday`` (Mon=0 … Sun=6), strictly after ``as_of``."""
    days = (weekday - as_of.weekday() + 7) % 7
    if days == 0:
        days = 7
    return as_of + timedelta(days=days)


def _phone10(rng: Random) -> str:
    # Fictional NANP 555-01xx block (informational / drama numbers).
    return f"55501{rng.randint(0, 9999):04d}"


def _format_phone10(digits: str) -> str:
    d = re.sub(r"\D", "", digits)
    if len(d) != 10:
        return digits
    return f"{d[0:3]}-{d[3:6]}-{d[6:10]}"


def _phone_spoken(digits: str) -> str:
    d = re.sub(r"\D", "", digits)
    words = {
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
    return " ".join(words[c] for c in d)


def _spell_name(name: str) -> str:
    parts: list[str] = []
    for ch in name:
        if ch == " ":
            parts.append("space")
        elif ch == "'":
            parts.append("apostrophe")
        else:
            parts.append(ch.upper())
    return " ".join(parts)


def build_bindings(
    rng: Random,
    *,
    as_of: date,
) -> dict[str, str]:
    name = rng.choice(_HARD_NAMES)
    phone = _phone10(rng)
    # Ensure exactly 10 digits
    phone = re.sub(r"\D", "", phone)[:10].ljust(10, "0")
    house = rng.randint(10, 9999)
    street = rng.choice(_STREETS)
    city_zip = f"{rng.choice(['Lakeside', 'Bayview', 'Hillcrest'])} {rng.randint(90000, 96999)}"
    address = f"{house} {street}, {city_zip}"
    next_tue = _next_weekday(as_of, 1)
    next_mon = _next_weekday(as_of, 0)
    next_wed = _next_weekday(as_of, 2)
    code = "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
    return {
        "name": name,
        "name_spelled": _spell_name(name),
        "phone10": phone,
        "phone": _format_phone10(phone),
        "phone_spoken": _phone_spoken(phone),
        "address": address,
        "next_tuesday": next_tue.isoformat(),
        "next_monday": next_mon.isoformat(),
        "next_wednesday": next_wed.isoformat(),
        "confirmation_code": code,
        "zip": str(rng.randint(90001, 96999)),
    }


def _subst(value: Any, bindings: dict[str, str]) -> Any:
    if isinstance(value, str):

        def repl(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in bindings:
                raise KeyError(f"unknown template key {{{{{key}}}}}")
            return bindings[key]

        return _TEMPLATE_RE.sub(repl, value)
    if isinstance(value, list):
        return [_subst(v, bindings) for v in value]
    if isinstance(value, dict):
        return {k: _subst(v, bindings) for k, v in value.items()}
    return value


def expand_scenario(
    scenario: Scenario,
    *,
    seed: int = 0,
    variant: int = 0,
    as_of: date | None = None,
) -> ExpandedScenario:
    """Deterministic expansion for ``(scenario.id, seed, variant)``."""
    anchor = as_of or date(2026, 9, 21)
    rng = _rng_for(scenario.id, seed, variant)
    bindings = build_bindings(rng, as_of=anchor)
    slots = _subst(scenario.slots, bindings)
    turns = [
        ScenarioTurn(
            caller=_subst(t.caller, bindings),
            pause_ms=t.pause_ms,
            barge_in_at_ms=t.barge_in_at_ms,
        )
        for t in scenario.turns
    ]
    expected_data = _subst(scenario.expected.model_dump(), bindings)
    expected = ScenarioExpected.model_validate(expected_data)
    gaps = list(scenario.kb_gaps)
    for key in expected.must_not_claim:
        gap = MUST_NOT_CLAIM_TO_GAP.get(key, key)
        if gap not in gaps:
            gaps.append(gap)
    return ExpandedScenario(
        scenario_id=scenario.id,
        seed=seed,
        variant=variant,
        intent=scenario.intent,
        slots=slots if isinstance(slots, dict) else {},
        turns=turns,
        expected=expected,
        tags=list(scenario.tags),
        kb_gaps=gaps,
        adversarial=scenario.adversarial,
        bindings=bindings,
    )


def validate_library(
    directory: Path | None = None,
    *,
    gap_doc: Path | None = None,
) -> list[Scenario]:
    """Load + validate all scenarios; ensure must_not_claim / kb_gaps exist in kb_gaps.md."""
    scenarios = load_all_scenarios(directory)
    gap_ids = load_kb_gap_ids(gap_doc)
    for sc in scenarios:
        for key in sc.expected.must_not_claim:
            gap = MUST_NOT_CLAIM_TO_GAP.get(key, key)
            if gap not in gap_ids:
                raise ValueError(f"{sc.id}: must_not_claim {key!r} → {gap} missing from kb_gaps.md")
        for gap in sc.kb_gaps:
            if gap not in gap_ids:
                raise ValueError(f"{sc.id}: kb_gaps entry {gap!r} missing from kb_gaps.md")
    return scenarios


__all__ = [
    "MUST_NOT_CLAIM_TO_GAP",
    "ExpandedScenario",
    "ExpectedToolCall",
    "Scenario",
    "ScenarioExpected",
    "ScenarioTurn",
    "expand_scenario",
    "load_all_scenarios",
    "load_kb_gap_ids",
    "load_scenario",
    "scenarios_dir",
    "validate_library",
]
