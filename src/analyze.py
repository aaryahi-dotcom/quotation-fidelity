"""
Summarise results/generations.csv.

Keeps the latest row per generation (company, fiscal year, theme, k, prompt
condition), ignores api_error rows, and re-applies the verifier's length rule
to stored quotations so rows written before that rule was added are classed
as pure_fabrication. Grounded = exact_match or fuzzy_match. Provenance
mismatches are reported separately, because the text is in the corpus but
attributed to the wrong chunk.

usage: python analyze.py [path/to/generations.csv]
"""
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

from verify import MIN_ALNUM_CHARS, normalise

DEFAULT = Path(__file__).parent.parent / "results" / "generations.csv"
GROUNDED = {"exact_match", "fuzzy_match"}


def latest_rows(path: Path) -> dict:
    latest = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if r["verification_outcome"] == "api_error":
                continue
            key = (r["company"], r["fiscal_year"], r["theme"], r["k"], r["prompt_condition"])
            latest[key] = r
    return latest


def effective_outcome(row: dict) -> str:
    quotation = row["quotation"]
    if quotation and sum(ch.isalnum() for ch in normalise(quotation)) < MIN_ALNUM_CHARS:
        return "pure_fabrication"
    return row["verification_outcome"]


def summarise(rows: dict) -> None:
    total = len(rows)
    outcomes = Counter(effective_outcome(r) for r in rows.values())
    grounded = sum(outcomes[o] for o in GROUNDED)
    print(f"Generations (latest, non-error): {total}")
    for o, n in outcomes.most_common():
        print(f"  {o:28s} {n:5d}  ({n / total:.1%})")
    print(f"Grounded rate (exact or fuzzy): {grounded / total:.1%}" if total else "No rows yet.")

    for dim, idx in [("theme", "theme"), ("k", "k"), ("prompt_condition", "prompt_condition")]:
        groups = defaultdict(list)
        for r in rows.values():
            groups[r[idx]].append(r)
        print(f"\nBy {dim}:")
        for g in sorted(groups):
            rs = groups[g]
            gr = sum(effective_outcome(r) in GROUNDED for r in rs)
            fab = sum(effective_outcome(r) == "pure_fabrication" for r in rs)
            print(f"  {g:45s} n={len(rs):3d}  grounded={gr / len(rs):.1%}  fabrication={fab / len(rs):.1%}")


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    summarise(latest_rows(path))
