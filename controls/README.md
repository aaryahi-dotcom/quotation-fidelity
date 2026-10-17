# Control sets

`calibrate.py` reads two files here, built by hand from the real corpus, plus
an optional paraphrase file. Current state (2026-10-17):

| File | Entries | Status |
|---|---|---|
| `positive.json` | 17 | Verbatim sentences, each matched to its chunk under text-flow extraction. Below the abstract's 20; `calibrate.py` requires at least 15 (`MIN_POSITIVE`). |
| `negative.json` | 20 | Plausible audit language absent from the corpus. Meets the abstract's 20. |
| `paraphrases_DRAFT.json` | 36 | Machine-drafted paraphrases, reviewed by the researcher on 2026-10-17: 29 keep, 2 fix, 5 reject. Used only with `calibrate.py --with-paraphrases`. Rejects stay in the file and are skipped. |
| `paraphrases_REVIEW.md` | — | The review sheet with the same verdicts, for reading alongside the JSON. |

## positive.json

Each entry is a sentence copied verbatim out of a real filing:

```json
{
  "quotation": "exact text copied from the filing",
  "chunk_id": "Infosys_2025_c0130",
  "context": "the full text of that chunk, as it would be supplied to the model",
  "company": "Infosys",
  "fiscal_year": "2025",
  "theme": "going-concern disclosures"
}
```

- `chunk_id` and `context` must come from the current chunking (`src/chunk.py`,
  text-flow extraction). Chunk IDs are numbered by position, so they change
  whenever extraction or chunking changes. Re-check every entry after any
  such change.
- The verifier must accept every positive at the exact-match stage. If one
  fails, fix the control or the normalisation before using any experiment data.
- Two entries have `theme` set to `none (out of study themes)`: the Infosys
  resource-conservation sentence and the Yes Bank group-capabilities sentence.
  They don't fit the five study themes, so they're kept for extraction checks
  only.
- The current set has 11 Infosys, 2 HUL, 2 TCS and 2 Yes Bank entries. There
  are no DHFL entries (the DHFL file is the 2017–18 report). Pledging has one
  entry, and that one is weak. Both points are limitations of the calibration.

## negative.json

Each entry is a sentence that is plausible financial or audit language and
does not appear anywhere in the corpus. The same shape as `positive.json`,
with `chunk_id` and `context` pointing at the chunk the model would be most
likely to cite. The check is that the quotation is absent from every chunk.

## Degraded variants

`calibrate.py`'s `degrade()` generates `word_swap` and `clause_drop` variants
from every positive. These are mechanical. Paraphrases are not generated
automatically. They come from `paraphrases_DRAFT.json`, which was machine-drafted
and then reviewed by the researcher. Only entries with `reviewed: true` and
`verdict` of `keep` or `fix` are used.
