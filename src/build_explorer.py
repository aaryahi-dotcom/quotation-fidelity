"""Build the data file for the pipeline explorer (docs/pipeline/).

Reads a generations CSV, re-chunks the corpus named in corpus/manifest.json
with the pipeline's own extractor and chunker, checks each row against the
chunk the model cited, and writes docs/pipeline/data.js as a plain script so
the page works when opened straight from disk (file://).

Only the chunks the rows cite are written out, so the data file stays small.
The chunk texts are the full text of each chunk, not a summary.

usage (from the project root):
    venv/bin/python src/build_explorer.py results/generations.csv
"""
import csv
import json
import sys
from collections import OrderedDict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from chunk import chunk_extraction  # noqa: E402
from extract import extract_pdf  # noqa: E402
from verify import normalise  # noqa: E402

OUT = ROOT / "docs" / "pipeline" / "data.js"
USABLE = {"exact_match", "fuzzy_match", "no_finding", "provenance_mismatch",
          "pure_fabrication", "unparsed_output", "schema_failure_after_retries"}


def load_rows(path: Path) -> list[dict]:
    """Keep the latest non-error row per generation key, as analyze.py does."""
    latest: "OrderedDict[tuple, dict]" = OrderedDict()
    with path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            if row["verification_outcome"] not in USABLE:
                continue
            key = (row["company"], row["fiscal_year"], row["theme"], row["k"],
                   row["prompt_condition"], row["model"])
            latest[key] = row
    return list(latest.values())


def build_chunks() -> dict[str, dict]:
    """Chunk every manifest filing with the pipeline's own code."""
    manifest = json.loads((ROOT / "corpus" / "manifest.json").read_text())
    chunks: dict[str, dict] = {}
    for item in manifest:
        pdf = ROOT / "corpus" / Path(item["path"]).name
        result = extract_pdf(str(pdf), item["company"], item["fiscal_year"])
        for c in chunk_extraction(result):
            chunks[c.chunk_id] = {
                "id": c.chunk_id, "company": c.company, "fiscal_year": c.fiscal_year,
                "page_start": c.page_start, "page_end": c.page_end,
                "section": c.section_heading, "text": c.text,
            }
    return chunks


def main() -> None:
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "results" / "generations.csv"
    rows = load_rows(csv_path)
    chunks = build_chunks()

    needed: set[str] = set()
    out_rows = []
    check = {"checked": 0, "exact_in_claimed": 0, "exact_elsewhere": 0,
             "exact_not_found": 0, "claimed_missing": 0}
    for r in rows:
        cited = r["claimed_chunk_id"].strip()
        matched = r["matched_chunk_id"].strip()
        quote = r["quotation"]
        if cited in chunks:
            needed.add(cited)
        else:
            check["claimed_missing"] += 1
        if matched in chunks:
            needed.add(matched)

        if quote and cited in chunks:
            check["checked"] += 1
            nq = normalise(quote)
            if nq in normalise(chunks[cited]["text"]):
                check["exact_in_claimed"] += 1
            elif any(nq in normalise(c["text"]) for c in chunks.values()):
                check["exact_elsewhere"] += 1
            else:
                check["exact_not_found"] += 1

        out_rows.append({
            "company": r["company"], "fiscal_year": r["fiscal_year"],
            "theme": r["theme"], "k": int(r["k"]),
            "prompt": r["prompt_condition"], "model": r["model"],
            "outcome": r["verification_outcome"], "quotation": quote,
            "score": float(r["match_score"]) if r["match_score"] else None,
            "cited": cited if cited in chunks else None,
            "matched": matched if matched in chunks else None,
            "attempts": int(r["attempts"]) if r["attempts"] else None,
        })

    payload = {
        "meta": {"source_csv": csv_path.name, "rows": len(out_rows),
                 "chunks_written": len(needed), "check": check},
        "generations": out_rows,
        "chunks": {cid: chunks[cid] for cid in sorted(needed)},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("window.EXPLORER = " + json.dumps(payload, ensure_ascii=False) + ";\n")
    print(f"rows: {len(out_rows)}  chunks written: {len(needed)}  check: {check}")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
