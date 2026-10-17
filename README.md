# Quotation Fidelity — standalone research pipeline

Research instrument for "Do Grounded Citations Actually Ground? Measuring
Quotation Fidelity in LLM-Based Forensic Analysis of Indian Annual Reports"
(seminar paper). Deliberately a separate, minimal pipeline from the RedShift
product (per the paper's own constraint that it must be an individual,
non-survey contribution) — but built to the same contract as RedShift's
Filing Analyst Agent (SRS/SDS v9, Component 3) so the thresholds this study
measures transfer directly into FR-31, the production grounding guard.

Last updated 2026-10-17. See `docs/technical-paper.md` for the full status,
decisions and limitations, and `RUNBOOK.md` for the run order.

## Pipeline stages (src/)

| Stage | File | Status |
|---|---|---|
| 1. PDF extraction | `extract.py` | Built and run on all seven PDFs. Uses text-flow order (`use_text_flow=True`) since 2026-10-17. |
| 2. Chunking | `chunk.py` | Built and run on all seven PDFs: 1,494 chunks in total. |
| 3. Embedding + FAISS index | `embed_index.py` | Written, **not run** — sentence-transformers/faiss-cpu not installed in this sandbox |
| 4. Generation (Gemini) | `generate.py` | Written, **not run** — no API key, package not installed |
| 5. Grounding verifier | `verify.py` | Built and tested — 4/4 smoke tests pass (pure stdlib, no deps). Threshold 0.80. |
| Calibration | `calibrate.py` | Built and run on the current controls (17 positive, 20 negative). `--with-paraphrases` adds the reviewed paraphrases. Refuses to run below 15 positive and 20 negative controls. |
| Held-out check | `heldout_check.py` | Built and run. A stability check only, since its controls were used to choose the threshold. |
| Orchestrator | `run_experiment.py` | Written, **not run** — depends on stages 3 and 4 |
| Analysis | `analyze.py` | Written, run after generation |

## Why stages 3-4 are untested here

This sandbox's network is allowlisted to package registries it already has
cached; `pip install sentence-transformers faiss-cpu google-genai`
and even smaller packages like `rapidfuzz` returned a hard 403 against
PyPI. `verify.py` was rewritten to use only the Python standard library
(`difflib`) so the core instrument — the grounding verifier itself — is
fully built and tested regardless. Stages 3 and 4 need an environment with
real internet and a Gemini API key; see "Next steps" below.

## What's real vs. what's a template

- `extract.py`, `chunk.py`, `verify.py`, `calibrate.py`, `heldout_check.py`:
  run on the real corpus or the smoke tests.
- `embed_index.py`, `generate.py`, `run_experiment.py`: written against the
  documented APIs of faiss/sentence-transformers/google-genai, believed
  correct, **not exercised**. Treat as a strong first draft, not finished code
  — run the self-tests in each file's `__main__` block the first time they're
  used somewhere those packages install, and fix whatever breaks.
- `corpus/manifest.json`: five usable filings (Infosys FY2025, TCS latest,
  HUL latest, Yes Bank FY2020, ILFS FY2018). DHFL and Manpasand are excluded.
- `controls/positive.json` (17 entries; the study stops here, and the abstract's 20 is a stated shortfall) and
  `controls/negative.json` (20 entries) exist and are verified against the
  current chunks. Details are in `controls/README.md`.

## Next steps, in order

1. **Positives stop at 17** (decision of 2026-10-17). The abstract commits to
   20; the shortfall is stated in the paper. Pledging and crisis-company
   coverage are limitations, not items to fix before the run.
2. **Decide how to report the threshold.** 0.80 was chosen on the same controls
   it is reported on, and it rejects 29 of 31 reviewed paraphrases. The paper
   has to state that the threshold covers extraction noise, not paraphrase.
3. **Re-run generation from scratch.** Move `results/generations.csv` aside
   first; the existing rows were made against the old chunk IDs.
4. **Get a Gemini API key** and an environment with real internet to install
   `sentence-transformers`, `faiss-cpu`, `google-genai` — most likely
   your own machine, rather than this sandbox.
5. Dry-run `run_experiment.py` on **one company, one theme, k=1** before the
   full grid.
6. Run the full grid (200 generations), then the adversarial-authorship
   variant (insert one steering sentence into 3-4 local copies, re-run, diff
   findings) — the adversarial variant is not yet implemented.
7. Analyse `results/generations.csv`: fabrication rate by theme / k / prompt
   condition, plus the inter-annotator-agreement pass on category-4 failures.
8. Write the paper around the real numbers.
