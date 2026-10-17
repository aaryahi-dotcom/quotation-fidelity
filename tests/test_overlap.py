"""Overlap rule for verify_quotation: the claimed chunk is checked first, at
both the exact and the fuzzy stage. Adjacent chunks share a 100-word overlap,
so a quotation inside the overlap matches two chunks; it must be labelled on
the claimed chunk.

Run from the project root:  venv/bin/python -m unittest tests/test_overlap.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from verify import Outcome, verify_quotation  # noqa: E402

SHARED = ("The auditors have drawn attention to a material uncertainty related to "
          "going concern in their report for the year ended 31 March 2020.")
CLAIMED_ONLY = "Loans and advances to group entities were disclosed in Note 42."
NEIGHBOUR_ONLY = "Capital commitments for the year are set out in Note 55."

# Two adjacent chunks that share the SHARED sentence in their overlap.
CHUNKS = {
    "C1": CLAIMED_ONLY + " " + SHARED,
    "C2": SHARED + " " + NEIGHBOUR_ONLY,
}


class OverlapExact(unittest.TestCase):
    def test_overlap_quote_claimed_first_is_exact_on_claimed(self):
        rec = verify_quotation(SHARED, "C1", CHUNKS)
        self.assertEqual(rec.outcome, Outcome.EXACT_MATCH)
        self.assertEqual(rec.matched_chunk_id, "C1")

    def test_overlap_quote_claimed_second_is_exact_on_claimed(self):
        rec = verify_quotation(SHARED, "C2", CHUNKS)
        self.assertEqual(rec.outcome, Outcome.EXACT_MATCH)
        self.assertEqual(rec.matched_chunk_id, "C2")

    def test_quote_only_in_neighbour_is_provenance_mismatch(self):
        rec = verify_quotation(NEIGHBOUR_ONLY, "C1", CHUNKS)
        self.assertEqual(rec.outcome, Outcome.PROVENANCE_MISMATCH)
        self.assertEqual(rec.matched_chunk_id, "C2")

    def test_claimed_chunk_missing_from_supplied_is_not_a_crash(self):
        rec = verify_quotation(CLAIMED_ONLY, "C9", CHUNKS)
        self.assertEqual(rec.outcome, Outcome.PROVENANCE_MISMATCH)
        self.assertEqual(rec.matched_chunk_id, "C1")


class OverlapFuzzy(unittest.TestCase):
    # A near-verbatim version of the overlap sentence: exact match fails, fuzzy
    # should score above the threshold on both chunks.
    NEAR = ("The auditors have drawn attention to a materiall uncertainty related to "
            "going concern in their report for the year ended 31 March 2020")

    def test_fuzzy_overlap_claimed_first_is_fuzzy_on_claimed(self):
        rec = verify_quotation(self.NEAR, "C2", CHUNKS)
        self.assertEqual(rec.outcome, Outcome.FUZZY_MATCH)
        self.assertEqual(rec.matched_chunk_id, "C2")

    def test_fuzzy_overlap_other_order_is_fuzzy_on_claimed(self):
        rec = verify_quotation(self.NEAR, "C1", CHUNKS)
        self.assertEqual(rec.outcome, Outcome.FUZZY_MATCH)
        self.assertEqual(rec.matched_chunk_id, "C1")

    def test_fuzzy_only_in_neighbour_is_provenance_mismatch(self):
        near_claimed_only = ("Loans and advances to group entitis were disclosed in Note 42")
        rec = verify_quotation(near_claimed_only, "C2", CHUNKS)
        self.assertEqual(rec.outcome, Outcome.PROVENANCE_MISMATCH)
        self.assertEqual(rec.matched_chunk_id, "C1")

    def test_nothing_close_is_pure_fabrication(self):
        rec = verify_quotation("The company has no contingent liabilities whatsoever this year",
                               "C1", CHUNKS)
        self.assertEqual(rec.outcome, Outcome.PURE_FABRICATION)
        self.assertIsNone(rec.matched_chunk_id)


if __name__ == "__main__":
    unittest.main()
