# Quotation Fidelity — standalone research pipeline

Research instrument for "Do Grounded Citations Actually Ground? Measuring
Quotation Fidelity in LLM-Based Forensic Analysis of Indian Annual Reports"
(seminar paper). Deliberately a separate, minimal pipeline from the RedShift
product (per the paper's own constraint that it must be an individual,
non-survey contribution) — but built to the same contract as RedShift's
Filing Analyst Agent (SRS/SDS v9, Component 3) so the thresholds this study
measures transfer directly into FR-31, the production grounding guard.

## Pipeline stages (src/)

| Stage | File | Status |
|---|---|---|
| 1. PDF extraction | `extract.py` | **Built, runnable now** (pdfplumber is installed) |
| 2. Chunking | `chunk.py` | **Built, runnable now** |
| 3. Embedding + FAISS index | `embed_index.py` | Written, **not run** — sentence-transformers/faiss-cpu not installed in this sandbox |
| 4. Generation (Gemini) | `generate.py` | Written, **not run** — no API key, package not installed |
| 5. Grounding verifier | `verify.py` | **Built and tested** — 4/4 smoke tests pass (pure stdlib, no deps) |
| Calibration | `calibrate.py` | **Built**, refuses to run without real control data (by design) |
| Orchestrator | `run_experiment.py` | Written, **not run** — depends on stages 3 and 4 |

## Why stages 3-4 are untested here

This sandbox's network is allowlisted to package registries it already has
cached; `pip install sentence-transformers faiss-cpu google-generativeai`
and even smaller packages like `rapidfuzz` returned a hard 403 against
PyPI. `verify.py` was rewritten to use only the Python standard library
(`difflib`) so the core instrument — the grounding verifier itself — is
fully built and tested regardless. Stages 3 and 4 need an environment with
real internet and a Gemini API key; see "Next steps" below.

## What's real vs. what's a template

- `extract.py`, `chunk.py`, `verify.py`, `calibrate.py`: actually run in this
  sandbox, including the verifier's smoke test (see `src/verify.py.__main__`).
- `embed_index.py`, `generate.py`, `run_experiment.py`: written against the
  documented APIs of faiss/sentence-transformers/google-generativeai, believed
  correct, **not exercised**. Treat as a strong first draft, not finished code
  — run the self-tests in each file's `__main__` block the first time they're
  used somewhere those packages install, and fix whatever breaks.
- `corpus/manifest.template.json`: fiscal years for the four distress
  companies are my best guess from the project's own backtest-case notes
  (Yes Bank 2020, DHFL 2019, IL&FS 2018, Manpasand 2018) — confirm these
  against the actual annual report you intend to use for each, since the
  exact filing (which fiscal year, which version if restated) changes what
  the pipeline measures.
- `controls/positive.json`, `controls/negative.json`: **do not exist yet**.
  These have to be built by hand from the real corpus (see `controls/README.md`).

## Next steps, in order

1. **Get the corpus.** Source the 7 (or up to 15) annual report PDFs. This
   sandbox cannot fetch arbitrary external sites (only package registries),
   so this needs either: PDFs uploaded directly to the chat, or your
   computer linked via the device bridge so they can be downloaded there.
2. **Get a Gemini API key** (free tier, Google AI Studio) and an environment
   with real internet to install `sentence-transformers`, `faiss-cpu`,
   `google-generativeai` — most likely your own machine, run through the
   device bridge, rather than this sandbox.
3. Run `extract.py` and `chunk.py` on one real PDF first; eyeball the output.
4. Hand-build `controls/positive.json` and `controls/negative.json` from
   that corpus (this is manual work — no shortcut).
5. Run `calibrate.py`, pick `FUZZY_THRESHOLD` from its sweep table, update
   `verify.py`.
6. Dry-run `run_experiment.py` on **one company, one theme, k=1** before the
   full grid — confirm the CSV row shape is actually what you want logged,
   since the full batch costs API quota and isn't worth re-running for a
   formatting fix.
7. Run the full grid, then the adversarial-authorship variant (insert one
   steering sentence into 3-4 local copies, re-run, diff findings).
8. Analyse `results/generations.csv`: fabrication rate by theme / k / prompt
   condition, plus the inter-annotator-agreement pass on category-4 failures.
9. Write the paper around the real numbers.
