"""
Orchestrator: runs the k x theme x prompt_condition grid for each filing in a
manifest and logs a verification record per generation. The grid per filing is
5 themes x 4 retrieval depths (k in {1,3,5,10}) x 2 prompt conditions = 40.
The study corpus has seven filings, so the full grid is 280 generations.

Resumable: generations already in results/generations.csv are skipped and new
rows are appended. A daily-quota error stops the run (exit code 3); restart it
the next day. Other API errors are logged as api_error rows and retried on the
next run.

Each SCHEMA_JSON attempt is a separate API request, so quota use can exceed
the generation count.
"""
from __future__ import annotations

import csv
import itertools
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from chunk import chunk_extraction
from embed_index import build_index, retrieve
from extract import extract_pdf
from generate import PromptCondition, THEMES, call_model
from verify import verify_quotation

K_VALUES = (1, 3, 5, 10)
MAX_WORKERS = 5
MIN_REQUEST_INTERVAL_S = 12.5  # free tier: 5 requests per minute
QUOTA_RETRIES = 5
QUOTA_BACKOFF_S = 65
PROMPT_CONDITIONS = (PromptCondition.FREE_FORM, PromptCondition.SCHEMA_JSON)

RESULTS_PATH = Path(__file__).parent.parent / "results" / "generations.csv"
ROW_FIELDS = [
    "company", "fiscal_year", "theme", "k", "prompt_condition",
    "claimed_chunk_id", "quotation", "verification_outcome", "match_score",
    "matched_chunk_id", "attempts", "latency_s",
]


_rate_lock = threading.Lock()
_last_request = [0.0]
_daily_quota_hit = threading.Event()


class DailyQuotaExhausted(RuntimeError):
    pass


def _call_throttled(theme, supplied, k, company, fiscal_year, condition):
    for _ in range(QUOTA_RETRIES):
        if _daily_quota_hit.is_set():
            raise DailyQuotaExhausted("daily quota already exhausted in this run")
        with _rate_lock:
            wait = _last_request[0] + MIN_REQUEST_INTERVAL_S - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            _last_request[0] = time.monotonic()
        try:
            return call_model(theme, supplied, k, company, fiscal_year, condition)
        except Exception as exc:
            message = str(exc)
            if "PerDay" in message:
                _daily_quota_hit.set()
                raise DailyQuotaExhausted(message) from exc
            if "quota" not in message.lower() and "429" not in message:
                raise
            time.sleep(QUOTA_BACKOFF_S)
    raise RuntimeError("Gemini quota retries exhausted")


def _job_key(company, fiscal_year, theme, k, condition):
    return (company, str(fiscal_year), theme, str(k), condition.value)


def load_done_keys() -> set:
    """Keys of generations already completed. api_error rows are not counted as
    done, so they are retried on the next run."""
    if not RESULTS_PATH.exists():
        return set()
    with open(RESULTS_PATH, newline="") as f:
        return {
            (r["company"], r["fiscal_year"], r["theme"], r["k"], r["prompt_condition"])
            for r in csv.DictReader(f)
            if r["verification_outcome"] != "api_error"
        }


def run_for_filing(pdf_path: str, company: str, fiscal_year: str,
                    writer: csv.DictWriter, done: set) -> None:
    extraction = extract_pdf(pdf_path, company, fiscal_year)
    if not extraction.extractable:
        print(f"SKIP {company} {fiscal_year}: extraction looks empty/scanned")
        return

    chunks = chunk_extraction(extraction)
    chunk_index = build_index(chunks)
    chunk_text_by_id = {c.chunk_id: c.text for c in chunks}

    jobs = [
        job for job in itertools.product(THEMES, K_VALUES, PROMPT_CONDITIONS)
        if _job_key(company, fiscal_year, job[0], job[1], job[2]) not in done
    ]
    print(f"  {len(jobs)} generations to run for {company} {fiscal_year}", flush=True)
    supplied_by_job = {}
    for theme, k, condition in jobs:
        retrieved = retrieve(chunk_index, theme, k)
        supplied_by_job[(theme, k, condition)] = {c.chunk_id: c.text for c in retrieved}

    def run_one(job: tuple) -> dict:
        theme, k, condition = job
        supplied = supplied_by_job[job]
        base = {
            "company": company, "fiscal_year": fiscal_year, "theme": theme,
            "k": k, "prompt_condition": condition.value,
            "claimed_chunk_id": "", "quotation": "",
            "verification_outcome": "", "match_score": "", "matched_chunk_id": "",
            "attempts": "", "latency_s": "",
        }
        try:
            gen = _call_throttled(theme, supplied, k, company, fiscal_year, condition)
        except DailyQuotaExhausted:
            raise
        except Exception as exc:
            base["verification_outcome"] = "api_error"
            base["quotation"] = f"{type(exc).__name__}: {exc}"[:300]
            return base

        row = dict(base)
        row["attempts"] = gen.attempts
        row["latency_s"] = f"{gen.latency_s:.2f}"

        if gen.parsed is None:
            row["verification_outcome"] = "schema_failure_after_retries"
            return row

        quotation = gen.parsed.get("verbatim_quotation", "")
        claimed_chunk = gen.parsed.get("chunk_id", "")
        row["claimed_chunk_id"], row["quotation"] = claimed_chunk, quotation

        if not quotation:
            row["verification_outcome"] = "no_finding"
        else:
            rec = verify_quotation(quotation, claimed_chunk, chunk_text_by_id)
            row["verification_outcome"] = rec.outcome.value
            row["match_score"] = f"{rec.match_score:.3f}"
            row["matched_chunk_id"] = rec.matched_chunk_id or ""
        return row

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(run_one, job) for job in jobs]
        for fut in as_completed(futures):
            writer.writerow(fut.result())


def main(corpus_manifest: list[dict]) -> int:
    """corpus_manifest: list of {"path": ..., "company": ..., "fiscal_year": ...}

    Appends to RESULTS_PATH and skips generations already recorded there, so a
    run stopped by the daily quota can be restarted without duplicate spend.
    Returns 0 when complete, 3 when stopped by the daily quota.
    """
    RESULTS_PATH.parent.mkdir(exist_ok=True)
    done = load_done_keys()
    is_new = not RESULTS_PATH.exists() or RESULTS_PATH.stat().st_size == 0
    with open(RESULTS_PATH, "a", newline="", buffering=1) as f:
        writer = csv.DictWriter(f, fieldnames=ROW_FIELDS)
        if is_new:
            writer.writeheader()
        try:
            for entry in corpus_manifest:
                print(f"Running {entry['company']} {entry['fiscal_year']}...", flush=True)
                run_for_filing(entry["path"], entry["company"], entry["fiscal_year"], writer, done)
        except DailyQuotaExhausted as exc:
            print(f"STOPPED: daily Gemini quota exhausted ({exc}). "
                  f"Rerun tomorrow; completed rows are kept and skipped.", flush=True)
            return 3
    print(f"Done. Results in {RESULTS_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 2:
        print("usage: python run_experiment.py <corpus_manifest.json>\n"
              "  manifest is a JSON list of {path, company, fiscal_year}")
        raise SystemExit(1)

    manifest = json.loads(Path(sys.argv[1]).read_text())
    raise SystemExit(main(manifest))
