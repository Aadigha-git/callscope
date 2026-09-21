"""ASR WER/CER scorers via jiwer after shared normalisation."""

from __future__ import annotations

from jiwer import process_characters, process_words

from callscope.eval.normalize import normalize
from callscope.eval.types import AsrScore


def score_asr(reference: str, hypothesis: str, *, already_normalized: bool = False) -> AsrScore:
    ref = reference if already_normalized else normalize(reference)
    hyp = hypothesis if already_normalized else normalize(hypothesis)
    if not ref and not hyp:
        return AsrScore(
            wer=0.0,
            cer=0.0,
            substitutions=0,
            deletions=0,
            insertions=0,
            hits=0,
            ref_words=0,
            hyp_words=0,
        )
    if not ref:
        # All hypothesis words are insertions
        words = hyp.split()
        chars = list(hyp.replace(" ", ""))
        return AsrScore(
            wer=1.0 if words else 0.0,
            cer=1.0 if chars else 0.0,
            substitutions=0,
            deletions=0,
            insertions=len(words),
            hits=0,
            ref_words=0,
            hyp_words=len(words),
        )
    w = process_words(ref, hyp)
    c = process_characters(ref, hyp)
    return AsrScore(
        wer=float(w.wer),
        cer=float(c.cer),
        substitutions=int(w.substitutions),
        deletions=int(w.deletions),
        insertions=int(w.insertions),
        hits=int(w.hits),
        ref_words=len(ref.split()),
        hyp_words=len(hyp.split()),
    )


def aggregate_asr(scores: list[AsrScore]) -> AsrScore:
    """Micro-average WER = sum(errors) / sum(ref words)."""
    if not scores:
        return score_asr("", "")
    subs = sum(s.substitutions for s in scores)
    dels = sum(s.deletions for s in scores)
    ins = sum(s.insertions for s in scores)
    hits = sum(s.hits for s in scores)
    ref_w = sum(s.ref_words for s in scores)
    hyp_w = sum(s.hyp_words for s in scores)
    errors = subs + dels + ins
    wer = (errors / ref_w) if ref_w else (0.0 if errors == 0 else 1.0)
    # CER micro-average approximated from per-turn cer weighted by ref words
    cer_num = sum(s.cer * max(s.ref_words, 1) for s in scores)
    cer_den = sum(max(s.ref_words, 1) for s in scores)
    return AsrScore(
        wer=wer,
        cer=cer_num / cer_den if cer_den else 0.0,
        substitutions=subs,
        deletions=dels,
        insertions=ins,
        hits=hits,
        ref_words=ref_w,
        hyp_words=hyp_w,
    )


__all__ = ["aggregate_asr", "score_asr"]
