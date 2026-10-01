"""
Verifier calibration: run this BEFORE any real experiment, on the real
corpus, to replace verify.FUZZY_THRESHOLD's placeholder value with a
measured one. Matches the abstract's methodology exactly:

  - 20 positive controls: strings copied verbatim from context -> verifier
    must accept all 20 (at the exact-match stage, score 1.0).
  - 20 negative controls: plausible financial language absent from the
    corpus -> verifier must reject all 20 (PURE_FABRICATION).
  - Corruption test: genuine quotes progressively degraded (word swap,
    clause drop, paraphrase) -> sweep the threshold and report
    precision/recall at each candidate value, so the chosen threshold is
    justified by a number, not a guess.

controls/positive.json and controls/negative.json are NOT included yet --
they have to be built from the real corpus (a positive control is a real
sentence copied out of a real filing; see controls/README.md). This script
will refuse to run meaningfully until they exist with real content.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from verify import FUZZY_THRESHOLD, normalise, verify_quotation, Outcome  # noqa: E402

CONTROLS_DIR = Path(__file__).parent.parent / "controls"


def load_controls() -> tuple[list[dict], list[dict]]:
    pos_path = CONTROLS_DIR / "positive.json"
    neg_path = CONTROLS_DIR / "negative.json"
    if not pos_path.exists() or not neg_path.exists():
        raise FileNotFoundError(
            f"Missing {pos_path} or {neg_path}. These must contain real "
            "quotations from the corpus (positive) and plausible-but-absent "
            "language (negative) -- see controls/README.md. Cannot calibrate "
            "against placeholder data; that would validate nothing."
        )
    positive = json.loads(pos_path.read_text())
    negative = json.loads(neg_path.read_text())
    if len(positive) < 20 or len(negative) < 20:
        print(f"WARNING: only {len(positive)} positive / {len(negative)} "
              f"negative controls -- the abstract commits to 20 of each.",
              file=sys.stderr)
    return positive, negative


def degrade(text: str, mode: str, rng: random.Random) -> str:
    """One corruption mode applied to a genuine quotation, for the fuzzy
    threshold sweep. `mode` in {"word_swap", "clause_drop", "paraphrase_stub"}.
    paraphrase_stub is a placeholder: real paraphrase degradation should be
    hand-written or LLM-generated per quotation, not algorithmic, since the
    point is to simulate a *plausible* near-miss, which random word deletion
    does not reliably produce.
    """
    words = text.split()
    if mode == "word_swap" and len(words) > 3:
        i, j = rng.sample(range(len(words)), 2)
        words[i], words[j] = words[j], words[i]
        return " ".join(words)
    if mode == "clause_drop" and len(words) > 6:
        cut = rng.randint(2, len(words) - 2)
        drop = rng.randint(1, 3)
        return " ".join(words[:cut] + words[cut + drop:])
    return text  # paraphrase_stub: caller should supply hand-written paraphrases


def run_control_check(positive: list[dict], negative: list[dict]) -> None:
    """Exact-match-only pass: positives should all hit EXACT_MATCH, negatives
    should all hit PURE_FABRICATION, using each control's own supplied
    context (the chunk(s) it should be checked against)."""
    failures = []

    for ctrl in positive:
        rec = verify_quotation(ctrl["quotation"], ctrl["chunk_id"],
                                {ctrl["chunk_id"]: ctrl["context"]})
        if rec.outcome != Outcome.EXACT_MATCH:
            failures.append(("positive", ctrl["quotation"], rec.outcome))

    for ctrl in negative:
        rec = verify_quotation(ctrl["quotation"], ctrl.get("chunk_id", "NA"),
                                {ctrl.get("chunk_id", "NA"): ctrl["context"]})
        if rec.outcome != Outcome.PURE_FABRICATION:
            failures.append(("negative", ctrl["quotation"], rec.outcome))

    print(f"Control check: {len(positive)} positive, {len(negative)} negative")
    if failures:
        print(f"{len(failures)} FAILURES (verifier is not ready to use):")
        for kind, q, outcome in failures:
            print(f"  [{kind}] {outcome.value}: {q[:70]!r}")
    else:
        print("All controls passed at the exact-match stage.")


def sweep_fuzzy_threshold(positive: list[dict], rng: random.Random,
                           candidates=(0.70, 0.75, 0.80, 0.85, 0.90, 0.95)) -> None:
    """Degrade each positive control and report, per threshold, how many
    degraded (should-still-match) and original (should-exact-match anyway)
    quotations are accepted. Pick the threshold reported here -- do not
    hand-pick one before seeing this table.
    """
    degraded_cases = []
    for ctrl in positive:
        for mode in ("word_swap", "clause_drop"):
            degraded_cases.append((degrade(ctrl["quotation"], mode, rng),
                                    ctrl["chunk_id"], ctrl["context"]))

    print(f"\nFuzzy threshold sweep over {len(degraded_cases)} degraded "
          f"positive-control variants:")
    print(f"{'threshold':>10} {'accepted':>10} {'rejected':>10}")
    for t in candidates:
        import verify as _v
        _v.FUZZY_THRESHOLD = t
        accepted = sum(
            1 for q, cid, ctx in degraded_cases
            if verify_quotation(q, cid, {cid: ctx}).outcome
            in (Outcome.EXACT_MATCH, Outcome.FUZZY_MATCH)
        )
        print(f"{t:>10.2f} {accepted:>10} {len(degraded_cases) - accepted:>10}")
    print(f"\n(placeholder FUZZY_THRESHOLD in verify.py is {FUZZY_THRESHOLD} "
          f"-- update it to the value chosen from this table, and record the "
          f"choice and its justification in the paper's methodology section.)")


if __name__ == "__main__":
    positive, negative = load_controls()
    run_control_check(positive, negative)
    sweep_fuzzy_threshold(positive, random.Random(42))
