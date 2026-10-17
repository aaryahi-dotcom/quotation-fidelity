# Known tooling state (recorded, not yet resolved):
#   - difflib.SequenceMatcher is used for fuzzy matching (decided 2026-10-17:
#     kept). rapidfuzz would change the fuzzy scores, so switching would need
#     recalibration of FUZZY_THRESHOLD. Limitation recorded in the paper.
#   - generate.py uses the google-genai SDK (migrated 2026-10-17); the
#     deprecated google-generativeai package is no longer used.
#   - The project venv runs Python 3.11 (standardised 2026-10-17).

"""
Stage 5: Grounding verifier (the paper's core instrument; = production FR-31).

Checks a returned verbatim_quotation against the chunk(s) actually supplied
to the model, in four stages, matching the methodology in the seminar
abstract:

  1. Exact match after normalisation (whitespace, quote marks, hyphenation).
  2. Fuzzy match at a calibrated threshold, to absorb PDF extraction noise.
  3. Provenance check: does the claimed chunk_id match where the quotation
     actually lives (it may be exact/fuzzy-matched in a DIFFERENT supplied
     chunk than the one cited)?
  4. Support check: left to manual annotation (see controls/ and
     results/annotation.csv) -- a quotation can be genuine and correctly
     attributed yet not actually support the stated finding. This module
     only flags candidates for that review; it does not automate it.

No third-party fuzzy-matching library is used (rapidfuzz could not be
installed in this sandbox -- see build-plan notes) -- difflib.SequenceMatcher
from the standard library stands in for it. difflib's ratio() is a close
analogue of rapidfuzz's token_sort/partial ratios for this use case (near-
verbatim text with minor word-level edits), but if rapidfuzz becomes
available later, swap `_fuzzy_ratio` and recalibrate FUZZY_THRESHOLD on the
corruption-test set before trusting old threshold values across the change.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

FUZZY_THRESHOLD = 0.80
# Chosen from calibrate.py's sweep on the control sets, and reported on those
# same controls, so it is not a validated constant. It handles near-verbatim
# extraction noise and word swaps; it does not reliably accept real
# paraphrases (see docs/technical-paper.md Section 8a).


class Outcome(str, Enum):
    EXACT_MATCH = "exact_match"
    FUZZY_MATCH = "fuzzy_match"
    PROVENANCE_MISMATCH = "provenance_mismatch"
    PURE_FABRICATION = "pure_fabrication"


@dataclass
class VerificationRecord:
    quotation: str
    claimed_chunk_id: str
    outcome: Outcome
    match_score: float          # 1.0 for exact, ratio for fuzzy, 0.0 for fabrication
    matched_chunk_id: str | None  # where it was actually found, if anywhere
    method: str                  # "exact" | "fuzzy" | "none"


def normalise(text: str) -> str:
    """Whitespace, quote-mark and hyphenation normalisation.

    - Unicode-normalise (NFKC) so visually-identical characters compare equal.
    - Collapse all whitespace runs to a single space.
    - Unify curly/smart quotes to straight quotes.
    - Rejoin words split by a hyphen at a line wrap (e.g. "account-\\ning"
      from a PDF extraction artefact becomes "accounting"). This is a
      heuristic: it also rejoins genuine compound words split at a line
      break, which is the correct behaviour for our purpose (we want to
      compare the *content*, not reproduce the PDF's line layout).
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("‘", "'").replace("’", "'")
    text = text.replace("“", '"').replace("”", '"')
    # rejoin hyphenated line-wrap breaks: "word- \n word" -> "wordword"
    text = re.sub(r"-\s+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.lower()


def _fuzzy_ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def _best_fuzzy_match(needle: str, haystack: str) -> float:
    """Best fuzzy ratio of `needle` against any substring of `haystack` of
    comparable length. difflib has no native substring search, so we slide
    a window sized to the needle (+/- a couple of words, to tolerate small
    insertions/deletions at the boundary) across the haystack, stepping one
    word at a time. This is O(n) windows at chunk scale (chunks are ~500-800
    words), which is fine for a one-off batch verification pass.

    The window must stay close to the needle's own length: padding it with
    many extra words (as an earlier version of this function did) dilutes
    the character-level ratio and silently depresses every score, which is
    the kind of bug a fuzzy-match calibration has to be run against real
    corruption-test data to catch -- see calibrate.py.

    Known cost: on a 750-word chunk this takes ~0.8s per quotation (measured
    on this sandbox's CPU). At k=10 with every quotation failing exact match,
    that is ~8s per generation purely in fuzzy verification -- acceptable for
    a one-off 200-generation batch (worst case ~27 CPU-minutes), but if it
    becomes a bottleneck, add a cheap difflib.quick_ratio() pre-filter before
    the full ratio() call, or port to rapidfuzz once PyPI is reachable.
    """
    needle_words = needle.split()
    hay_words = haystack.split()
    n = len(needle_words)
    if n == 0:
        return 0.0
    if len(hay_words) <= n:
        return _fuzzy_ratio(needle, haystack)

    slack = max(1, n // 10)  # tolerate a small length mismatch, not a large one
    best = 0.0
    for lo in range(0, len(hay_words) - n + 1):
        for width in (n - slack, n, n + slack):
            width = max(1, width)
            window = " ".join(hay_words[lo:lo + width])
            best = max(best, _fuzzy_ratio(needle, window))
    return best


MIN_ALNUM_CHARS = 10


def verify_quotation(
    quotation: str,
    claimed_chunk_id: str,
    supplied_chunks: dict[str, str],   # chunk_id -> chunk text, as given to the LLM
) -> VerificationRecord:
    """Run the four-stage check (support/stage-4 excluded; see module docstring)."""
    q_norm = normalise(quotation)
    if sum(ch.isalnum() for ch in q_norm) < MIN_ALNUM_CHARS:
        return VerificationRecord(quotation, claimed_chunk_id,
                                   Outcome.PURE_FABRICATION, 0.0, None, "too_short")

    # Stage 1+3 combined: exact match. Prefer the claimed chunk, because
    # adjacent chunks share a 100-word overlap and a quotation inside it occurs
    # in both. Only if the claimed chunk does not contain it do we look at the
    # other supplied chunks, which is a provenance mismatch.
    claimed_text = supplied_chunks.get(claimed_chunk_id)
    if claimed_text is not None and q_norm in normalise(claimed_text):
        return VerificationRecord(quotation, claimed_chunk_id,
                                   Outcome.EXACT_MATCH, 1.0, claimed_chunk_id, "exact")
    for chunk_id, chunk_text in supplied_chunks.items():
        if chunk_id != claimed_chunk_id and q_norm in normalise(chunk_text):
            return VerificationRecord(quotation, claimed_chunk_id,
                                       Outcome.PROVENANCE_MISMATCH, 1.0, chunk_id, "exact")

    # Stage 2: fuzzy match, with the same claimed-chunk-first rule as stage 1.
    # Scores are computed once per chunk; the claimed chunk is decided first.
    scores = {cid: _best_fuzzy_match(q_norm, normalise(text))
              for cid, text in supplied_chunks.items()}
    claimed_score = scores.get(claimed_chunk_id, 0.0)
    if claimed_score >= FUZZY_THRESHOLD:
        return VerificationRecord(quotation, claimed_chunk_id, Outcome.FUZZY_MATCH,
                                   claimed_score, claimed_chunk_id, "fuzzy")

    other_id, other_score = max(
        ((cid, s) for cid, s in scores.items() if cid != claimed_chunk_id),
        key=lambda pair: pair[1], default=(None, 0.0))
    if other_score >= FUZZY_THRESHOLD:
        return VerificationRecord(quotation, claimed_chunk_id, Outcome.PROVENANCE_MISMATCH,
                                   other_score, other_id, "fuzzy")

    best_score = max(scores.values(), default=0.0)
    return VerificationRecord(quotation, claimed_chunk_id,
                               Outcome.PURE_FABRICATION, best_score, None, "none")


if __name__ == "__main__":
    # Smoke test with synthetic data -- exercises every branch without
    # needing the real corpus or any external package.
    chunks = {
        "C1": "The Company's statutory auditors have included an emphasis of "
              "matter regarding material uncertainty related to going concern "
              "in their report for the year ended 31 March 2020.",
        "C2": "Related party transactions during the year comprised loans "
              "and advances to group entities disclosed in Note 42.",
    }

    tests = [
        ("material uncertainty related to going concern", "C1", Outcome.EXACT_MATCH),
        ("material uncertainty related to going concern", "C2", Outcome.PROVENANCE_MISMATCH),
        ("materiall uncertainty relatd to going concren", "C1", Outcome.FUZZY_MATCH),
        ("the company has no contingent liabilities whatsoever this year", "C1", Outcome.PURE_FABRICATION),
    ]

    passed = 0
    for quote, claimed, expected in tests:
        rec = verify_quotation(quote, claimed, chunks)
        ok = rec.outcome == expected
        passed += ok
        print(f"{'OK ' if ok else 'FAIL'} expected={expected.value:20s} "
              f"got={rec.outcome.value:20s} score={rec.match_score:.2f}  {quote[:50]!r}")
    print(f"\n{passed}/{len(tests)} smoke tests passed")
