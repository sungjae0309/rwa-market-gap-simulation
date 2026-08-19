"""Load reviewed assumptions separately from the legacy scenario ledger."""

from __future__ import annotations

from pathlib import Path

from rwa_market_gap.commodity_oracle.evidence import VerifiedInputLedger


DEFAULT_REVIEWED_INPUT_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "reviewed_commodity_economics"
    / "assumptions.json"
)


def load_reviewed_inputs(
    path: str | Path = DEFAULT_REVIEWED_INPUT_PATH,
) -> VerifiedInputLedger:
    ledger = VerifiedInputLedger.load(path)
    ledger.assert_complete()
    return ledger
