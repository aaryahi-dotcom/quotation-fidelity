"""
Stage 2: Chunking.

Splits extracted pages into overlapping passages of 500-800 tokens, each
tagged with company, fiscal year, page number, section heading, and a unique
chunk identifier -- matching the production Filing Analyst Agent's chunking
contract (RedShift SRS/SDS v9, Component 3) so this study's grounding
measurements transfer directly to the production grounding guard (FR-31).

Token counts here use whitespace-splitting as a cheap proxy for tokens
(roughly 0.75 words/token for English text is the usual rule of thumb, but
we keep units as "words" throughout and simply treat the 500-800 figure as
a words-per-chunk target; this is a documented simplification, not a claim
of exact tokenizer parity with the embedding model).
"""
from __future__ import annotations

from dataclasses import dataclass

from extract import ExtractionResult, Page

MIN_WORDS = 500
MAX_WORDS = 800
OVERLAP_WORDS = 100  # words of overlap carried into the next chunk


@dataclass
class Chunk:
    chunk_id: str
    company: str
    fiscal_year: str
    page_start: int
    page_end: int
    section_heading: str | None
    text: str
    word_count: int


def _flatten_words(pages: list[Page]) -> list[tuple[str, int, str | None]]:
    """Return a flat list of (word, page_number, section_heading)."""
    out: list[tuple[str, int, str | None]] = []
    for page in pages:
        for word in page.text.split():
            out.append((word, page.page_number, page.section_heading))
    return out


def chunk_extraction(result: ExtractionResult) -> list[Chunk]:
    words = _flatten_words(result.pages)
    chunks: list[Chunk] = []
    i = 0
    idx = 0
    n = len(words)

    while i < n:
        end = min(i + MAX_WORDS, n)
        window = words[i:end]

        # Don't emit a tail chunk under MIN_WORDS unless it's genuinely the
        # end of the document (merge it into the previous chunk instead).
        if len(window) < MIN_WORDS and chunks and end == n:
            prev = chunks[-1]
            merged_text = prev.text + " " + " ".join(w for w, _, _ in window)
            chunks[-1] = Chunk(
                chunk_id=prev.chunk_id,
                company=prev.company,
                fiscal_year=prev.fiscal_year,
                page_start=prev.page_start,
                page_end=window[-1][1] if window else prev.page_end,
                section_heading=prev.section_heading,
                text=merged_text,
                word_count=prev.word_count + len(window),
            )
            break

        text = " ".join(w for w, _, _ in window)
        page_start = window[0][1]
        page_end = window[-1][1]
        # Section heading for the chunk: the heading in force at its first word.
        section_heading = window[0][2]

        idx += 1
        chunk_id = f"{result.company}_{result.fiscal_year}_c{idx:04d}"
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                company=result.company,
                fiscal_year=result.fiscal_year,
                page_start=page_start,
                page_end=page_end,
                section_heading=section_heading,
                text=text,
                word_count=len(window),
            )
        )

        if end == n:
            break
        i = end - OVERLAP_WORDS  # step forward, retaining the overlap

    return chunks


if __name__ == "__main__":
    import sys

    from extract import extract_pdf

    if len(sys.argv) != 4:
        print("usage: python chunk.py <pdf_path> <company> <fiscal_year>")
        raise SystemExit(1)

    result = extract_pdf(sys.argv[1], sys.argv[2], sys.argv[3])
    chunks = chunk_extraction(result)
    print(f"{len(chunks)} chunks from {len(result.pages)} pages")
    for c in chunks[:3]:
        print(f"  {c.chunk_id} pp{c.page_start}-{c.page_end} "
              f"[{c.section_heading}] {c.word_count}w: {c.text[:80]!r}")
