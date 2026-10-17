# Runbook

Run everything from the project root with the virtualenv active. Scripts in `src/` assume they are run from `src/`. Last updated 2026-10-17.

## 0. Setup

```bash
cd quotation-fidelity
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
echo "GEMINI_API_KEY=your-key" > .env          # never commit this file
set -a && source .env && set +a
```

## 1. Corpus

Seven PDFs live in `corpus/` (PDFs are git-ignored). Five are usable. Each must match its label on the cover page before use.

| File | Label | Status |
|---|---|---|
| infosys-fy2025.pdf | Infosys 2025 | verified |
| tcs-latest.pdf | TCS 2026 (FY ending Mar 2026) | verified |
| hul-latest.pdf | HUL 2026 (FY ending Mar 2026) | verified |
| yes-bank-fy2020.pdf | YesBank 2020 | verified |
| ilfs-fy2018.pdf | ILFS 2018 | verified from the body text: year ended 31 March 2018 (FY2018, FY 2017-18), with 2017 as comparative |
| dhfl-fy2019.pdf | DHFL | **do not use**: the file is the 2017-18 report |
| manpasand-fy2018.pdf | Manpasand 2018 | **hold**: partial text layer |

`corpus/manifest.json` lists the five usable filings. Add DHFL and Manpasand only after they are replaced or fixed.

**Extraction.** `src/extract.py` uses `extract_text(use_text_flow=True)`, which follows the PDF's content order. The default order interleaves two-column layouts and splits sentences that wrap across columns. The switch was made on 2026-10-17. Chunks produced before that date have different chunk IDs and must be regenerated (see Section 4).

## 2. Controls

- `controls/positive.json`: 17 verbatim sentences, each matched to a chunk under text-flow extraction. **The set stops at 17 by decision (2026-10-17). The abstract commits to 20; this shortfall is stated in the paper.** `calibrate.py` requires at least 15 (`MIN_POSITIVE`).
- `controls/negative.json`: 20 plausible sentences absent from the corpus.
- `controls/paraphrases_DRAFT.json`: 36 machine-drafted paraphrases, reviewed on 2026-10-17 (29 keep, 2 fix, 5 reject). Only `keep` and `fix` entries are used, and only with `--with-paraphrases`.

After any change to extraction or chunking, check that each positive still matches its chunk and update `chunk_id` and `context` where the text has moved. See `controls/README.md`.

## 3. Calibration and threshold

```bash
cd src
python3 calibrate.py                    # exact-match check plus mechanical fuzzy sweep
python3 calibrate.py --with-paraphrases # same, plus the reviewed paraphrases
python3 heldout_check.py                # stability check on a stratified held-out half
```

`FUZZY_THRESHOLD` in `src/verify.py` is 0.80. It is the lowest tested threshold with no negative control accepted. It was chosen on the same controls it is reported on, so it is not a validated constant. At 0.80 the reviewed real paraphrases are mostly rejected (2 of 31 accepted), so the threshold handles extraction noise and word-level edits, not paraphrase. See `docs/technical-paper.md` Section 8a for the numbers and the scope limit.

## 4. Generation (resumable, daily quota)

```bash
cd src
python3 run_experiment.py ../corpus/manifest.json
```

- Each filing gives 40 generations (5 themes x k in {1,3,5,10} x 2 prompt conditions). The five-filing manifest gives 200.
- Completed generations in `results/generations.csv` are skipped, so the command can be rerun as often as needed.
- **Before the first run after the extraction change, move the existing CSV aside.** The 25 rows already in `results/generations.csv` were generated against the old chunk IDs and are not valid for the current chunks.
- The free Gemini tier allows 20 requests a day for the model. A daily-limit error stops the run with exit code 3. Rerun the next day.
- SCHEMA_JSON retries are separate requests, so the quota can run out before 20 generations.
- Other API errors are written as `api_error` rows and retried on the next run.

## 5. Results

```bash
cd src
python3 analyze.py
```

Keeps the latest non-error row per generation and reports grounded and fabrication rates by theme, k and prompt condition. Grounded = exact or fuzzy match. Provenance mismatches are reported separately.

## 6. Dashboard

```bash
cd ~/quotation-fidelity
python3 -m http.server 8000 --bind 127.0.0.1
```

Open http://localhost:8000/dashboard/ to see progress against the expected 200 generations.

## 7. Paper

`docs/technical-paper.md` is the process and status report. It contains no experimental results until the full run is analysed.
