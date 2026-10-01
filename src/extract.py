"""
Stage 1: PDF extraction.

Extracts text from an annual report PDF with page-level metadata, mirroring
the production Filing Analyst Agent's extraction step (RedShift SRS/SDS v9,
Component 3): page number and section heading are preserved on every chunk
of text so later retrieval results can be traced back to their source.

This module uses pdfplumber only (the production system's CPU-only primary
extractor). The production system falls back to a layout-aware VLM
(Granite-Docling) for scanned/image-only filings; that fallback is out of
scope for this standalone research pipeline, which assumes machine-generated,
text-extractable PDFs (per the corpus note in the seminar paper: all filings
are from public BSE/NSE repositories as native PDFs, not scans).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pdfplumber

# A "section heading" line in an Indian annual report is typically short,
# in caps or title case, and does not end in a full stop. This is a coarse
# heuristic, not a layout parser -- good enough for retrieval metadata, not
# claimed to be a perfect outline extractor.
_HEADING_RE = re.compile(
    r"^(?:[A-Z][A-Za-z&,\-\s]{2,80}|[0-9]+\.\s*[A-Z][A-Za-z&,\-\s]{2,80})$"
)


@dataclass
class Page:
    company: str
    fiscal_year: str
    page_number: int           # 1-indexed
    text: str
    section_heading: str | None  # last heading seen at or before this page


@dataclass
class ExtractionResult:
    company: str
    fiscal_year: str
    source_path: str
    pages: list[Page] = field(default_factory=list)
    extractable: bool = True   # False if pdfplumber yields ~no text (likely scanned)


def _looks_like_heading(line: str) -> bool:
    line = line.strip()
    if not (3 <= len(line) <= 90):
        return False
    return bool(_HEADING_RE.match(line))


def extract_pdf(path: str, company: str, fiscal_year: str) -> ExtractionResult:
    """Extract text page by page, carrying forward the most recent heading.

    Records a filing as non-extractable (mirrors FR-13's "unprocessable"
    handling) when the total extracted text is below a trivial threshold,
    which is the signature of a scanned/image-only PDF that pdfplumber
    cannot read.
    """
    pages: list[Page] = []
    current_heading: str | None = None
    total_chars = 0

    with pdfplumber.open(path) as pdf:
        for i, pdf_page in enumerate(pdf.pages, start=1):
            text = pdf_page.extract_text() or ""
            total_chars += len(text)

            for line in text.splitlines():
                if _looks_like_heading(line):
                    current_heading = line.strip()
                    break  # first candidate heading on the page is enough

            pages.append(
                Page(
                    company=company,
                    fiscal_year=fiscal_year,
                    page_number=i,
                    text=text,
                    section_heading=current_heading,
                )
            )

    # Heuristic threshold: fewer than ~200 chars/page on average is almost
    # certainly a scan pdfplumber could not read.
    extractable = (total_chars / max(len(pages), 1)) > 200

    return ExtractionResult(
        company=company,
        fiscal_year=fiscal_year,
        source_path=path,
        pages=pages,
        extractable=extractable,
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 4:
        print("usage: python extract.py <pdf_path> <company> <fiscal_year>")
        raise SystemExit(1)

    result = extract_pdf(sys.argv[1], sys.argv[2], sys.argv[3])
    print(f"{result.company} {result.fiscal_year}: "
          f"{len(result.pages)} pages, extractable={result.extractable}")
    for p in result.pages[:3]:
        preview = p.text[:120].replace("\n", " ")
        print(f"  p{p.page_number} [{p.section_heading}]: {preview!r}")
