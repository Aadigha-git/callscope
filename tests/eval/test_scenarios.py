"""Scenario library validation and deterministic expansion (T-M3-01)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from callscope.eval.scenarios import (
    MUST_NOT_CLAIM_TO_GAP,
    Scenario,
    expand_scenario,
    load_all_scenarios,
    load_kb_gap_ids,
    scenarios_dir,
    validate_library,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
AS_OF = date(2026, 9, 21)
EXPECTED_IDS = frozenset(
    {
        "book_simple",
        "book_with_correction",
        "no_availability_alternative",
        "reschedule",
        "cancel",
        "faq_in_kb",
        "faq_not_in_kb",
        "callback_request",
        "human_handoff",
        "multi_intent",
        "barge_in_mid_sentence",
        "silence_no_response",
        "adv_prompt_injection",
        "adv_cross_customer",
        "adv_out_of_scope",
        "adv_abuse",
    }
)
ADVERSARIAL_IDS = frozenset(
    {
        "adv_prompt_injection",
        "adv_cross_customer",
        "adv_out_of_scope",
        "adv_abuse",
    }
)


@pytest.fixture(scope="module")
def scenarios() -> list[Scenario]:
    return validate_library()


def test_library_has_sixteen_scenarios(scenarios: list[Scenario]) -> None:
    ids = {s.id for s in scenarios}
    assert len(scenarios) == 16
    assert ids == EXPECTED_IDS


def test_adversarial_coverage(scenarios: list[Scenario]) -> None:
    adv = {s.id for s in scenarios if s.adversarial}
    assert adv == ADVERSARIAL_IDS
    tags_by_id = {s.id: set(s.tags) for s in scenarios if s.adversarial}
    assert "injection" in tags_by_id["adv_prompt_injection"]
    assert "privacy" in tags_by_id["adv_cross_customer"]
    assert "out_of_scope" in tags_by_id["adv_out_of_scope"]
    assert "abuse" in tags_by_id["adv_abuse"]


def test_barge_in_and_silence_present(scenarios: list[Scenario]) -> None:
    by_id = {s.id: s for s in scenarios}
    assert any(t.barge_in_at_ms is not None for t in by_id["barge_in_mid_sentence"].turns)
    assert any(t.pause_ms is not None for t in by_id["silence_no_response"].turns)


def test_every_yaml_validates(scenarios: list[Scenario]) -> None:
    for path in sorted(scenarios_dir().glob("*.yaml")):
        data = path.read_text(encoding="utf-8")
        assert data.strip(), path
    assert len(scenarios) == len(list(scenarios_dir().glob("*.yaml")))


def test_must_not_claim_keys_in_kb_gaps(scenarios: list[Scenario]) -> None:
    gap_ids = load_kb_gap_ids()
    for sc in scenarios:
        for key in sc.expected.must_not_claim:
            gap = MUST_NOT_CLAIM_TO_GAP.get(key, key)
            assert gap in gap_ids, f"{sc.id}: {key} → {gap}"


def test_expansion_deterministic(scenarios: list[Scenario]) -> None:
    for sc in scenarios:
        a = expand_scenario(sc, seed=7, variant=2, as_of=AS_OF)
        b = expand_scenario(sc, seed=7, variant=2, as_of=AS_OF)
        assert a.model_dump() == b.model_dump()
        c = expand_scenario(sc, seed=7, variant=3, as_of=AS_OF)
        assert a.bindings != c.bindings or sc.id.startswith("adv_")


def test_templates_substituted(scenarios: list[Scenario]) -> None:
    book = next(s for s in scenarios if s.id == "book_with_correction")
    expanded = expand_scenario(book, seed=1, variant=0, as_of=AS_OF)
    joined = " ".join(t.caller for t in expanded.turns)
    assert "{{" not in joined
    assert expanded.bindings["name"] in joined or expanded.bindings["name_spelled"] in joined
    assert expanded.slots["phone"] == expanded.bindings["phone10"]
    assert expanded.slots["date"] == expanded.bindings["next_tuesday"]
    # next Tuesday after 2026-09-21 (Mon) is 2026-09-22
    assert expanded.bindings["next_tuesday"] == "2026-09-22"


def test_unknown_must_not_claim_rejected() -> None:
    with pytest.raises(ValidationError, match="must_not_claim"):
        Scenario.model_validate(
            {
                "id": "bad",
                "intent": "x",
                "turns": [{"caller": "hi"}],
                "expected": {"must_not_claim": ["not_a_real_gap"]},
            }
        )


def test_load_all_from_default_dir() -> None:
    loaded = load_all_scenarios()
    assert {s.id for s in loaded} == EXPECTED_IDS


def test_repo_scenarios_dir() -> None:
    assert scenarios_dir() == REPO_ROOT / "eval" / "scenarios"


def test_load_scenario_rejects_non_mapping(tmp_path: Path) -> None:
    from callscope.eval.scenarios import load_scenario

    path = tmp_path / "bad.yaml"
    path.write_text("- just a list\n", encoding="utf-8")
    with pytest.raises(ValueError, match="expected mapping"):
        load_scenario(path)


def test_empty_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no scenario"):
        load_all_scenarios(tmp_path)


def test_unknown_template_key() -> None:
    sc = Scenario.model_validate(
        {"id": "t", "intent": "x", "turns": [{"caller": "hi {{unknown_key}}"}]}
    )
    with pytest.raises(KeyError, match="unknown_key"):
        expand_scenario(sc, seed=0, variant=0, as_of=AS_OF)


def test_validate_library_rejects_missing_gap(tmp_path: Path) -> None:
    (tmp_path / "s.yaml").write_text(
        "id: s\nintent: x\nturns:\n  - caller: hi\nkb_gaps: [GAP-NOT-REAL]\n",
        encoding="utf-8",
    )
    gaps = tmp_path / "gaps.md"
    gaps.write_text("| GAP-PRICE-EXACT | x | y |\n", encoding="utf-8")
    with pytest.raises(ValueError, match="GAP-NOT-REAL"):
        validate_library(tmp_path, gap_doc=gaps)
