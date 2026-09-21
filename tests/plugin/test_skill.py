"""Receptionist skill + prompt hash tests (T-M2-04)."""

from __future__ import annotations

from pathlib import Path

import yaml
from hermes_callscope import register
from hermes_callscope.skill import SKILL_NAME, assembled_prompt, prompt_hash, skill_text


def test_skill_contains_guardrails() -> None:
    text = skill_text().lower()
    assert "one question at a time" in text
    assert "confirmed=true" in text
    assert "lookup_faq" in text
    assert "never invent" in text or "do not have that information" in text
    assert "ignore" in text and "instructions" in text


def test_prompt_hash_stable() -> None:
    a = prompt_hash()
    b = prompt_hash()
    assert len(a) == 64
    assert a == b
    assert a == __import__("hashlib").sha256(assembled_prompt().encode()).hexdigest()


def test_register_skill_when_supported() -> None:
    skills: list[tuple[str, str]] = []

    class Ctx:
        def register_tool(self, **kwargs: object) -> None:
            _ = kwargs

        def register_hook(self, name: str, fn: object) -> None:
            _ = (name, fn)

        def register_skill(self, *, name: str, content: str) -> None:
            skills.append((name, content))

    register(Ctx())
    assert skills
    assert skills[0][0] == SKILL_NAME
    assert "Lakeside" in skills[0][1]


def test_manual_runs_cover_ten_scenarios() -> None:
    root = Path(__file__).resolve().parents[2] / "eval" / "manual_runs"
    files = sorted(root.glob("*.yaml"))
    assert len(files) == 10
    unknown = yaml.safe_load((root / "07_faq_unknown.yaml").read_text(encoding="utf-8"))
    assert unknown["acceptance"] == "unknown_fact_declines"
    inj = yaml.safe_load((root / "10_injection.yaml").read_text(encoding="utf-8"))
    assert inj["acceptance"] == "injection_refused"
