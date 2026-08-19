from __future__ import annotations

from copy import deepcopy
import unittest

from rwa_market_gap.commodity_oracle.evidence import VerifiedInputLedger


class EvidenceLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = VerifiedInputLedger.load()

    def test_every_input_has_source_grade_unit_definition_and_date(self) -> None:
        self.ledger.assert_complete()
        self.assertGreater(len(self.ledger.records), 0)
        for record in self.ledger.records:
            self.assertIn(record.grade, {"A", "B", "C", "X"})
            self.assertTrue(record.source)
            self.assertTrue(record.unit)
            self.assertTrue(record.definition)
            self.assertTrue(record.as_of)

    def test_grade_c_assumptions_have_sensitivity_ranges(self) -> None:
        assumptions = [
            record
            for record in self.ledger.records
            if record.grade == "C" and record.label == "assumption"
        ]
        self.assertGreater(len(assumptions), 0)
        self.assertTrue(all(record.sensitivity is not None for record in assumptions))

    def test_grade_x_input_cannot_be_consumed(self) -> None:
        payload = deepcopy(self.ledger.payload)
        payload["analysis"]["unverified"] = {
            "value": 1,
            "unit": "unknown",
            "definition": "Deliberately unresolved test record.",
            "grade": "X",
            "source": "unresolved-items register",
            "as_of": "2026-08-14"
        }
        ledger = VerifiedInputLedger(payload, source_path=self.ledger.source_path)
        with self.assertRaises(ValueError):
            ledger.value("analysis.unverified")


if __name__ == "__main__":
    unittest.main()
