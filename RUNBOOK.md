# Runbook

Run everything from the project root with the virtualenv active. Scripts in `src/` assume they are run from `src/`.

## 0. Setup

```bash
cd quotation-fidelity
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
echo "GEMINI_API_KEY=your-key" > .env          # never commit this file
set -a && source .env && set +a
```

## 1. Corpus

Seven filings live in `corpus/` (PDFs are git-ignored). Each must match its label on the cover page before use.

| File | Label | Status |
|---|---|---|
| infosys-fy2025.pdf | Infosys 2025 | verified |
| tcs-latest.pdf | TCS 2026 (FY ending Mar 2026) | verified |
| hul-latest.pdf | HUL 2026 (FY ending Mar 2026) | verified |
| yes-bank-fy2020.pdf | YesBank 2020 | verified |
| ilfs-fy2018.pdf | ILFS 2018 | verified (FY2018, confirmed by the researcher) |
| dhfl-fy2019.pdf | DHFL | **do not use**: the file is the 2017-18 report |
| manpasand-fy2018.pdf | Manpasand 2018 | **hold**: partial text layer |

`corpus/manifest.json` lists the filings to run. It currently includes the five usable filings. Add DHFL and Manpasand only after they are replaced or fixed.

## 2. Controls

- `controls/positive.json`: 18 verbatim sentences, each checked against its source chunk.
- `controls/negative.json`: 20 plausible sentences absent from the corpus.
- `controls/paraphrases_DRAFT.json`: 36 machine-drafted paraphrases, **unreviewed**. Check each one before it is used in calibration.

## 3. Calibration and threshold

```bash
cd src
python3 calibrate.py          # exact-match check plus fuzzy sweep (slow: several minutes)
python3 heldout_check.py      # threshold check on a stratified held-out half
```

`FUZZY_THRESHOLD` in `src/verify.py` is 0.80. It is the lowest tested threshold with no negative control accepted (0.70 and 0.75 accept the 0.759 negative). It was chosen on the same controls it is reported on, so it is not a validated constant. It must be re-examined once a control set exists that was not used to choose the threshold. See `docs/technical-paper.md` Section 8a.

## 4. Generation (resumable, daily quota)

```bash
cd src
python3 run_experiment.py ../corpus/manifest.json
```

- Each filing gives 40 generations (5 themes x k in {1,3,5,10} x 2 prompt conditions). The five-filing manifest gives 200.
- Completed generations in `results/generations.csv` are skipped, so the command can be rerun as often as needed.
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
