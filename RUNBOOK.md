# Runbook — run this on a machine with real internet (e.g. your own, via Claude Code)

This sandbox that built the code could not install sentence-transformers,
faiss-cpu or google-generativeai, and could not fetch external PDFs (PyPI
and general web access are both blocked). Everything below assumes you're
now in an environment that CAN reach the internet normally.

## 0. Setup

```bash
cd quotation-fidelity
python3 -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt
export GEMINI_API_KEY="your-key-from-ai.google.dev"   # free tier
```

If `pip install` fails on `faiss-cpu` on your OS, see FAISS's install docs —
it occasionally needs `pip install faiss-cpu --no-cache-dir` or a conda
install instead.

## 1. Get the corpus

Download these into `corpus/`. I found candidate direct links via web
search but have **not opened or verified any of these PDFs myself** —
check the fiscal year printed on page 1 of each against the table below
before trusting it, especially for DHFL and Manpasand where the search
results were ambiguous.

| Company | Target fiscal year | Best candidate link found | Confidence |
|---|---|---|---|
| Yes Bank | FY2019-20 | https://www.bseindia.com/bseplus/annualreport/532648/5326480320.pdf | Medium — BSE's own annual report archive for scrip 532648, filename suggests FY20 |
| DHFL | FY2018-19 | https://www.bseindia.com/bseplus/AnnualReport/511072/5110720318.pdf | Low — verify the year on the cover page; BSE scrip is 511072 if you need to browse their archive directly |
| IL&FS | FY2017-18 | https://www.ilfsindia.com/media/2022/annual-report-fy-2018.pdf | Medium-high — official IL&FS site, filename says "annual-report-fy-2018" |
| Manpasand Beverages | FY2017-18 | https://trendlyne.com/fundamentals/documents-annual-reports/1751/MANPASAND/manpasand-beverages-ltd/ | Low — this is an archive index page, not a direct PDF; BSE scrip is 539207 if you need to search BSE's own archive |
| Infosys | most recent (FY2024-25) | https://www.infosys.com/investors/reports-filings/annual-report/annual/documents/infosys-ar-25.pdf | High — official Infosys investor relations page |
| TCS | most recent | https://www.tcs.com/investor-relations/financial-statements (browse from here to the Annual Report section) | Low — no single direct PDF link surfaced in search |
| Hindustan Unilever | most recent | https://www.hul.co.in/investors/annual-reports-and-performance-highlights/annual-reports/ | High — official HUL investor relations page, browse to the integrated annual report PDF |

If a link is dead or wrong, BSE's own per-company annual report archive
(`bseindia.com`, search the scrip code) and each company's own investor
relations page are the two reliable fallbacks — avoid Scribd/third-party
mirrors where possible since page numbers and OCR quality are unverified
there.

Once downloaded, fill in `corpus/manifest.json` (copy
`manifest.template.json`, fix the paths and the two "fyXXXX" control years).

## 2. Sanity-check extraction on ONE real PDF first

```bash
cd src
python3 extract.py ../corpus/infosys_fy2025.pdf Infosys 2025
python3 chunk.py ../corpus/infosys_fy2025.pdf Infosys 2025
```
Read the printed previews. If section headings look wrong or text looks
garbled, the filing may be partially scanned — check `extractable` in the
output before trusting it.

## 3. Build control sets (manual — no shortcut)

Open 2-3 of the real filings. Hand-copy 20+ genuine sentences into
`controls/positive.json` (format in `controls/README.md`) spread across the
five themes, and hand-write 20+ plausible-but-absent sentences into
`controls/negative.json`. This is the part that actually validates the
verifier — don't skip or minimize it.

## 4. Calibrate

```bash
python3 calibrate.py
```
Read the exact-match pass/fail list first — fix `verify.py`'s `normalise()`
if anything fails there before even looking at the fuzzy sweep. Then pick
`FUZZY_THRESHOLD` from the sweep table (don't just take the sandbox's
placeholder 0.85) and update it in `verify.py`.

## 5. Dry run

Build a 1-entry manifest (just Infosys, say) and run:
```bash
python3 run_experiment.py ../corpus/manifest_dryrun.json
```
Open `results/generations.csv`. Confirm the columns are actually what you
want logged before spending quota on the full batch — Gemini's free tier
has rate limits, and 600 generations is not cheap to redo.

## 6. Full run

```bash
python3 run_experiment.py ../corpus/manifest.json
```
This can take a while (API latency x up to 600 calls, plus the fuzzy
verifier's own cost on long chunks — see the performance note in
`verify.py`). Consider running it in the background / overnight.

## 7. Adversarial authorship test

Make local copies of 3-4 filings with one steering sentence inserted (e.g.
softening a going-concern line without deleting it). Re-run the pipeline on
just those copies with a distinct `fiscal_year` tag (e.g. `"2020_adv"`) so
the results don't overwrite the baseline, and diff the findings.

## 8. Human labelling + analysis

For every row verified as EXACT_MATCH or FUZZY_MATCH, a second pass (you,
plus ideally one other annotator — a teammate works) judges whether the
quotation actually *supports* the stated finding (category 4,
"unsupported attribution"). Compute inter-annotator agreement (Cohen's
kappa) on a shared subset. Then aggregate `results/generations.csv` into
fabrication rate by theme / k / prompt condition, and test the four stated
hypotheses (H1-H4 in the abstract) against the real numbers.

## 9. Write the paper

Extend the current two-page abstract (ask Claude for this once results
exist) into the full technical paper: Introduction, Related Work,
Methodology (now describable in past tense, with the real calibrated
threshold and control-set sizes), Results (tables/plots from step 8),
Discussion and Limitations, Conclusion. The References list from the
abstract carries over; add any paper you end up relying on more heavily
during writing.
