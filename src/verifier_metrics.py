"""Verifier-level classification metrics on the control sets.

Run from the project root or from src/:  venv/bin/python src/verifier_metrics.py

Positives: genuine quotations (17 originals), mechanically degraded copies
(word swap and clause drop, same RNG order as calibrate.py, seed 42), and
reviewed paraphrases (keep/fix, source present). Negatives: the 20 fabricated
controls. The score is verify.verify_quotation's match_score against each
item's own chunk, which is the calibration setup.
"""
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent  # src/
sys.path.insert(0, str(HERE))
import calibrate  # noqa: E402
from verify import verify_quotation, FUZZY_THRESHOLD  # noqa: E402

THRESH = FUZZY_THRESHOLD
positive, negative = calibrate.load_controls()
rng = random.Random(42)

def score(q, cid, ctx):
    return verify_quotation(q, cid, {cid: ctx}).match_score

orig = [score(c["quotation"], c["chunk_id"], c["context"]) for c in positive]
mech = []
for c in positive:
    for mode in ("word_swap", "clause_drop"):
        t = calibrate.degrade(c["quotation"], mode, rng)
        mech.append(score(t, c["chunk_id"], c["context"]))
para_cases = calibrate.load_paraphrases(positive)
para = [score(t, cid, ctx) for t, cid, ctx in para_cases]
neg = [score(n["quotation"], n["chunk_id"], n["context"]) for n in negative]

def auc(pos, neg):
    # Mann-Whitney U: P(score_pos > score_neg) + 0.5 * P(tie)
    wins = 0.0
    for p in pos:
        for n in neg:
            wins += 1.0 if p > n else (0.5 if p == n else 0.0)
    return wins / (len(pos) * len(neg))

def report(name, pos):
    tp = sum(s >= THRESH for s in pos); fn = len(pos) - tp
    fp = sum(s >= THRESH for s in neg); tn = len(neg) - fp
    prec = tp / (tp + fp) if tp + fp else float("nan")
    rec = tp / (tp + fn) if tp + fn else float("nan")
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else float("nan")
    acc = (tp + tn) / (len(pos) + len(neg))
    fpr = fp / (fp + tn)
    print(f"{name}: n_pos={len(pos)} n_neg={len(neg)} AUC={auc(pos, neg):.3f} "
          f"@{THRESH:.2f}: TP={tp} FN={fn} FP={fp} TN={tn} "
          f"precision={prec:.3f} recall={rec:.3f} F1={f1:.3f} acc={acc:.3f} FPR={fpr:.3f}")

print(f"threshold {THRESH}; positives orig={len(orig)} mech={len(mech)} para={len(para)}")
print("min/max neg score:", round(min(neg), 3), round(max(neg), 3))
report("A originals only (exact)", orig)
report("B originals + mechanical (51 positives)", orig + mech)
report("C originals + mechanical + paraphrases (77)", orig + mech + para)
report("D paraphrases only (26)", para)
report("E mechanical only (34)", mech)
