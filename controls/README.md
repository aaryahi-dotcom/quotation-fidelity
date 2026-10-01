# Control sets

`calibrate.py` needs two files here, neither of which exists yet because
they have to be built from the real corpus:

## positive.json

20+ entries, each a sentence (or short run of sentences) **copied verbatim**
out of a real filing. Format:

```json
[
  {
    "quotation": "exact text copied from the filing",
    "chunk_id": "YesBank_2020_c0042",
    "context": "the full text of that chunk, as it would be supplied to the model"
  }
]
```

Pick these by hand while reading the filings for theme coverage (aim for a
spread across all five themes and all seven companies, not all from one
filing). The verifier must accept all of these at the exact-match stage —
if any fail, something in `normalise()` is wrong, fix it before touching
any real experiment data.

## negative.json

20+ entries, each a sentence that is **plausible financial/audit language
but does not appear anywhere in the corpus** — e.g. a going-concern sentence
phrased slightly differently from how any of the seven filings actually
phrase it. Same shape as positive.json (chunk_id/context can point at
whatever chunk you'd plausibly expect the model to cite, since the point is
that the quotation itself is absent from it).

## Degraded/corruption variants

`calibrate.py`'s `degrade()` function auto-generates `word_swap` and
`clause_drop` variants from positive.json. It does NOT auto-generate
paraphrase variants — those should be hand-written (3-5 per positive
control is plenty) because a *plausible* paraphrase needs human judgement,
not random word deletion. Add a `paraphrases` field to any positive.json
entry you've paraphrased by hand if you want calibrate.py to sweep those too
(not yet wired up — extend `sweep_fuzzy_threshold` when you add them).
