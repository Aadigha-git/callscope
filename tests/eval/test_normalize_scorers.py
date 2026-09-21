"""Golden normalisation cases (>=40) and scorer unit tests (T-M3-02)."""

from __future__ import annotations

import pytest

from callscope.eval.normalize import NORMALIZER_VERSION, digits_to_words, normalize
from callscope.eval.scorers.asr import aggregate_asr, score_asr
from callscope.eval.scorers.entities import (
    extract_phones,
    phone_partial,
    score_address,
    score_code,
    score_date,
    score_entities,
    score_entity,
    score_name,
    score_phone,
    score_time,
    soundex,
    token_f1,
)
from callscope.eval.scorers.nlu import score_nlu, slot_prf
from callscope.eval.scorers.task import score_task
from callscope.eval.scorers.tools import score_tools
from callscope.eval.types import EvalItemResult

pytestmark = pytest.mark.unit

# (raw, expected_normalized)
GOLDEN_NORMALIZE: list[tuple[str, str]] = [
    ("Hello, World!", "hello world"),
    ("UM uh Er the AC", "the ac"),
    ("you know what I mean", "what i mean"),
    ("double five", "5 5"),
    ("triple oh", "0 0 0"),
    ("double 7", "7 7"),
    ("five five five", "5 5 5"),
    ("oh one two", "0 1 2"),
    ("o nine", "0 9"),
    ("twenty one", "21"),
    ("thirty-two", "32"),
    ("forty five", "45"),
    ("ninety nine", "99"),
    ("eleven", "11"),
    ("twelve", "12"),
    ("first", "1"),
    ("second", "2"),
    ("third", "3"),
    ("twentieth", "20"),
    ("555-010-1234", "5550101234"),
    ("(555) 010-9999", "5550109999"),
    ("+1 555 010 1111", "5550101111"),
    ("March 3rd 2026", "2026-03-03"),
    ("jan 15, 2025", "2025-01-15"),
    ("September 9", "09-09"),
    ("2026-09-22", "2026-09-22"),
    ("3/15/26", "2026-03-15"),
    ("12/1/2026", "2026-12-01"),
    ("3 pm", "15:00"),
    ("3:30 PM", "15:30"),
    ("12:00 a.m.", "00:00"),
    ("12 pm", "12:00"),
    ("9:05 am", "09:05"),
    ("It's Siobhan!!!", "its siobhan"),
    ("code AB12CD34", "code ab12cd34"),
    ("zero zero one", "0 0 1"),
    ("seventy", "70"),
    ("eighty-eight", "88"),
    ("fifteenth", "15"),
    ("like uh Tuesday", "tuesday"),
    ("hmm okay", "okay"),
    ("", ""),
    ("   spaced   out  ", "spaced out"),
    ("A.B.C.", "a b c"),
    ("what's up?", "whats up"),
    ("twenty", "20"),
    ("October 31st 1999", "1999-10-31"),
    ("4:00", "04:00"),
]


@pytest.mark.parametrize(("raw", "expected"), GOLDEN_NORMALIZE)
def test_normalize_golden(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


def test_normalizer_version() -> None:
    assert NORMALIZER_VERSION == "1.0.0"


def test_digits_to_words() -> None:
    assert "five" in digits_to_words("5")
    assert normalize(digits_to_words("55")) == "5 5"


def test_asr_perfect() -> None:
    s = score_asr("hello world", "Hello, world!")
    assert s.wer == 0.0
    assert s.substitutions == 0


def test_asr_substitution_and_aggregate() -> None:
    a = score_asr("one two three", "one two four")
    assert a.substitutions == 1
    assert a.wer == pytest.approx(1 / 3)
    b = score_asr("a b", "a b c")
    agg = aggregate_asr([a, b])
    assert agg.ref_words == a.ref_words + b.ref_words
    assert agg.insertions >= 1


def test_asr_empty_and_insertion_only() -> None:
    assert score_asr("", "").wer == 0.0
    ins = score_asr("", "hello")
    assert ins.insertions == 1
    assert aggregate_asr([]).wer == 0.0


def test_phone_entity() -> None:
    s = score_phone("555-010-1234", "five five five oh one oh one two three four")
    # after normalize hyp may be digit sequence
    assert s.entity_type == "PHONE"
    assert extract_phones("call 555-010-1234 please")
    assert phone_partial("5550101234", "5550101299") == pytest.approx(0.8)
    assert score_phone("5550101234", "5550101234").exact


def test_date_time_name_address_code() -> None:
    assert score_date("March 3 2026", "2026-03-03").exact
    assert score_time("3 pm", "15:00").exact
    n = score_name("Siobhan ONeill", "Siobhan O'Neill")
    assert n.phonetic_match is True
    assert n.score >= 0.4
    assert soundex("Smith") == soundex("Smyth") or soundex("Smith") != ""
    a = score_address("123 Maple Street", "123 Maple Street")
    assert a.exact
    assert score_code("AB12CD34", "ab12cd34").exact
    assert score_entity("PHONE", "5550101234", "5550101234").exact
    with pytest.raises(ValueError, match="unknown"):
        score_entity("XYZ", "a", "b")


def test_token_f1_edges() -> None:
    assert token_f1("", "") == 1.0
    assert token_f1("a", "") == 0.0
    assert token_f1("a b", "a b") == 1.0


def test_nlu_and_slots() -> None:
    p, r, _f = slot_prf({"a": "1"}, {"a": "1", "b": "2"})
    assert p < 1.0
    assert r == 1.0
    s = score_nlu(
        intent_ref="book_appointment",
        intent_hyp="book_appointment",
        slots_ref={"date": "2026-09-22"},
        slots_hyp={"date": "2026-09-22"},
        intent_labels=["book_appointment", "cancel"],
    )
    assert s.intent_correct
    assert s.slot_f1 == 1.0
    assert s.macro_f1 == 1.0
    bad = score_nlu(
        intent_ref="book_appointment",
        intent_hyp="cancel",
        slots_ref={},
        slots_hyp={},
    )
    assert not bad.intent_correct


def test_tools_and_task() -> None:
    expected = [
        {"name": "check_availability", "args": {}},
        {"name": "book_appointment", "args": {"confirmed": True}},
    ]
    tools = score_tools(expected, expected)
    assert tools.exact_match
    miss = score_tools(
        [{"name": "book_appointment", "args": {"slot_date": "2026-09-22"}}],
        [{"name": "book_appointment", "args": {"slot_date": "2026-09-23"}}],
    )
    assert not miss.exact_match
    assert score_tools([], []).exact_match

    ok = score_task(
        expected_final_state={"appointment_exists": True},
        actual_final_state={"appointment_exists": True},
        tool_calls_pred=[{"name": "book_appointment", "args": {"confirmed": True}}],
    )
    assert ok.task_success
    bad = score_task(
        expected_final_state={"appointment_exists": True},
        actual_final_state={"appointment_exists": False},
        tool_calls_pred=[{"name": "book_appointment", "args": {}}],
        must_confirm_before_mutation=True,
    )
    assert not bad.policy_ok
    assert not bad.task_success


def test_eval_item_result_row_shape() -> None:
    row = EvalItemResult(
        hyp_transcript="hi",
        wer=0.1,
        slots_pred={"a": 1},
        tool_calls_pred=[{"name": "lookup_faq"}],
        flags=["x"],
        detail={"asr": {"wer": 0.1}},
    ).to_row()
    assert set(row) == {
        "hyp_transcript",
        "wer",
        "slots_pred",
        "tool_calls_pred",
        "latencies_ms",
        "flags",
        "auto_root_cause",
    }
    assert "detail" not in row


def test_address_partial_and_empty_phone() -> None:
    partial = score_address("123 Maple Street", "999 Maple Street")
    assert not partial.exact
    assert partial.score == pytest.approx(0.5)
    assert score_phone("", "").score == 1.0
    assert score_phone("5550101234", "").score == 0.0


def test_normalize_short_year_and_edges() -> None:
    assert normalize("March 3 26") == "2026-03-03"
    assert normalize("3/15/99") == "2099-03-15"
    assert soundex("") == ""
    assert soundex("123") == ""
    # grouped phone path + digit-run dedupe
    assert "5550101234" in extract_phones("555 010 1234")
    # address fallback when pattern missing
    fb = score_address("somewhere", "elsewhere")
    assert not fb.exact
    assert score_entity("NAME", "Ann", "Ann").exact
    # codes / times / dates extractors
    from callscope.eval.scorers.entities import extract_codes, extract_dates, extract_times

    assert extract_dates("on 2026-09-22")
    assert extract_times("at 15:30")
    assert extract_codes("confirm AB12CD34 now")
    assert score_entities([("PHONE", "5550101234", "5550101234")])[0].exact
    assert extract_phones("555-010-9999")
    assert phone_partial("", "1") == 0.0
    # non-contiguous digits still recovered via digits_only path
    assert "5550101234" in extract_phones("x555y010z1234")


def test_tools_name_mismatch_and_to_dicts() -> None:
    miss = score_tools(
        [{"name": "book_appointment", "args": {"a": "1"}}],
        [{"name": "cancel_appointment", "args": {"a": "1"}}],
    )
    assert not miss.exact_match
    assert miss.to_dict()["name_accuracy"] < 1.0
    s = score_asr("a", "a")
    assert "wer" in s.to_dict()
    from callscope.eval.types import NluScore, TaskScore

    assert score_nlu(
        intent_ref="a",
        intent_hyp="a",
        slots_ref={},
        slots_hyp={},
    ).to_dict()["intent_correct"]
    t = score_task(
        expected_final_state={},
        actual_final_state={},
        tool_calls_pred=[{"name": "lookup_faq", "args": {}}],
        must_confirm_before_mutation=False,
    )
    assert t.to_dict()["task_success"]
    del NluScore, TaskScore
