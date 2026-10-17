"""
Held-out check of FUZZY_THRESHOLD on the control sets.

Splits positives and negatives into a calibration half and a held-out half,
stratified by theme, with a fixed seed. Reports, on the held-out half only,
how many degraded positives and negatives the current threshold accepts.

Caveat: the threshold was chosen after inspecting the sweep on all controls,
so this is a stability check, not an independent test. A fair test needs
controls written after the threshold was fixed.

usage: python heldout_check.py
"""
import json
import random
from collections import defaultdict
from pathlib import Path

import verify
from calibrate import degrade
from verify import Outcome, verify_quotation

CONTROLS = Path(__file__).parent.parent / "controls"
SEED = 42


def stratified_halves(items: list[dict], rng: random.Random) -> tuple[list, list]:
    by_theme = defaultdict(list)
    for it in items:
        by_theme[it["theme"]].append(it)
    cal, held = [], []
    for theme in sorted(by_theme):
        group = by_theme[theme][:]
        rng.shuffle(group)
        half = len(group) // 2
        cal.extend(group[:half])
        held.extend(group[half:])
    return cal, held


def accepted(quotation: str, chunk_id: str, context: str) -> bool:
    rec = verify_quotation(quotation, chunk_id, {chunk_id: context})
    return rec.outcome in (Outcome.EXACT_MATCH, Outcome.FUZZY_MATCH)


def main() -> None:
    rng = random.Random(SEED)
    positives = json.loads((CONTROLS / "positive.json").read_text())
    negatives = json.loads((CONTROLS / "negative.json").read_text())

    pos_cal, pos_held = stratified_halves(positives, rng)
    neg_cal, neg_held = stratified_halves(negatives, rng)
    print(f"positives: calibration {len(pos_cal)}, held-out {len(pos_held)}")
    print(f"negatives: calibration {len(neg_cal)}, held-out {len(neg_held)}")
    print(f"threshold in verify.py: {verify.FUZZY_THRESHOLD}")

    deg_rng = random.Random(SEED)
    degraded = [(degrade(p["quotation"], m, deg_rng), p["chunk_id"], p["context"])
                for p in pos_held for m in ("word_swap", "clause_drop")]

    pos_ok = sum(accepted(p["quotation"], p["chunk_id"], p["context"]) for p in pos_held)
    deg_ok = sum(accepted(q, c, x) for q, c, x in degraded)
    neg_bad = sum(accepted(n["quotation"], n["chunk_id"], n["context"]) for n in neg_held)

    print(f"\nHeld-out at threshold {verify.FUZZY_THRESHOLD}:")
    print(f"  original positives accepted:  {pos_ok}/{len(pos_held)}")
    print(f"  degraded positives accepted:  {deg_ok}/{len(degraded)}")
    print(f"  negatives accepted (should be 0): {neg_bad}/{len(neg_held)}")


if __name__ == "__main__":
    main()
