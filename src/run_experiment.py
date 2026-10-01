"""
Orchestrator: runs the full k x theme x prompt_condition grid across the
corpus and logs a verification record for every generation, matching the
abstract's design: up to 15 companies x 5 themes x 4 retrieval depths
(k in {1,3,5,10}) x 2 prompt conditions = up to 600 generations.

STATUS: NOT executed. Depends on embed_index.py and generate.py, neither of
which has run end-to-end in this sandbox (see their module docstrings).
Wire this up and do a 1-company, 1-theme, k=1 dry run FIRST -- do not launch
the full 600-generation batch until that dry run's output has been read by
a person and the row format confirmed, since each row costs API quota and
the batch cannot be meaningfully "undone" once spent on a bad prompt.
"""
from __future__ import annotations

import csv
import itertools
from pathlib import Path

from chunk import chunk_extraction
from embed_index import build_index, retrieve
from extract import extract_pdf
from generate import PromptCondition, THEMES, call_model
from verify import verify_quotation

K_VALUES = (1, 3, 5, 10)
PROMPT_CONDITIONS = (PromptCondition.FREE_FORM, PromptCondition.SCHEMA_JSON)

RESULTS_PATH = Path(__file__).parent.parent / "results" / "generations.csv"
ROW_FIELDS = [
    "company", "fiscal_year", "theme", "k", "prompt_condition",
    "claimed_chunk_id", "quotation", "verification_outcome", "match_score",
    "matched_chunk_id", "attempts", "latency_s",
]


def run_for_filing(pdf_path: str, company: str, fiscal_year: str,
                    writer: csv.DictWriter) -> None:
    extraction = extract_pdf(pdf_path, company, fiscal_year)
    if not extraction.extractable:
        print(f"SKIP {company} {fiscal_year}: extraction looks empty/scanned")
        return

    chunks = chunk_extraction(extraction)
    chunk_index = build_index(chunks)
    chunk_text_by_id = {c.chunk_id: c.text for c in chunks}

    for theme, k, condition in itertools.product(THEMES, K_VALUES, PROMPT_CONDITIONS):
        retrieved = retrieve(chunk_index, theme, k)
        supplied = {c.chunk_id: c.text for c in retrieved}

        gen = call_model(theme, supplied, k, company, fiscal_year, condition)

        if gen.parsed is None:
            writer.writerow({
                "company": company, "fiscal_year": fiscal_year, "theme": theme,
                "k": k, "prompt_condition": condition.value,
                "claimed_chunk_id": "", "quotation": "",
                "verification_outcome": "schema_failure_after_retries",
                "match_score": "", "matched_chunk_id": "",
                "attempts": gen.attempts, "latency_s": f"{gen.latency_s:.2f}",
            })
            continue

        quotation = gen.parsed.get("verbatim_quotation", "")
        claimed_chunk = gen.parsed.get("chunk_id", "")

        if not quotation:
            outcome, score, matched = "no_finding", "", ""
        else:
            rec = verify_quotation(quotation, claimed_chunk, chunk_text_by_id)
            outcome, score, matched = rec.outcome.value, f"{rec.match_score:.3f}", rec.matched_chunk_id or ""

        writer.writerow({
            "company": company, "fiscal_year": fiscal_year, "theme": theme,
            "k": k, "prompt_condition": condition.value,
            "claimed_chunk_id": claimed_chunk, "quotation": quotation,
            "verification_outcome": outcome, "match_score": score,
            "matched_chunk_id": matched, "attempts": gen.attempts,
            "latency_s": f"{gen.latency_s:.2f}",
        })


def main(corpus_manifest: list[dict]) -> None:
    """corpus_manifest: list of {"path": ..., "company": ..., "fiscal_year": ...}"""
    RESULTS_PATH.parent.mkdir(exist_ok=True)
    with open(RESULTS_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ROW_FIELDS)
        writer.writeheader()
        for entry in corpus_manifest:
            print(f"Running {entry['company']} {entry['fiscal_year']}...")
            run_for_filing(entry["path"], entry["company"], entry["fiscal_year"], writer)
    print(f"Done. Results written to {RESULTS_PATH}")


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 2:
        print("usage: python run_experiment.py <corpus_manifest.json>\n"
              "  manifest is a JSON list of {path, company, fiscal_year}")
        raise SystemExit(1)

    manifest = json.loads(Path(sys.argv[1]).read_text())
    main(manifest)
