"""Load assumptions for the public commodity simulation."""

from __future__ import annotations

from pathlib import Path

from .evidence import VerifiedInputLedger


DEFAULT_ASSUMPTION_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "commodity_simulation"
    / "assumptions.json"
)


def load_assumptions(
    path: str | Path = DEFAULT_ASSUMPTION_PATH,
) -> VerifiedInputLedger:
    ledger = VerifiedInputLedger.load(path)
    ledger.assert_complete()
    return ledger
