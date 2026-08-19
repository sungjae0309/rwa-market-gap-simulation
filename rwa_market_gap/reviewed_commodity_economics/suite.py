"""Facade for the separately reviewed commodity economics package."""

from __future__ import annotations

from dataclasses import dataclass

from rwa_market_gap.commodity_oracle.evidence import VerifiedInputLedger

from .gold import GoldFalsificationEconomics, GoldStressAssumptions
from .inputs import load_reviewed_inputs
from .natural_gas import NaturalGasEvidenceReview
from .wti import WTIStressAssumptions, WTIStressEconomics


@dataclass(frozen=True)
class ReviewedSuite:
    wti: WTIStressEconomics
    gold: GoldFalsificationEconomics
    natural_gas: NaturalGasEvidenceReview


class ReviewedCommodityEconomicsEngine:
    def __init__(
        self,
        evidence: VerifiedInputLedger | None = None,
        assumptions: VerifiedInputLedger | None = None,
    ) -> None:
        self.evidence = evidence or VerifiedInputLedger.load()
        self.assumptions = assumptions or load_reviewed_inputs()
        self.evidence.assert_complete()
        self.assumptions.assert_complete()

    def build(self) -> ReviewedSuite:
        return ReviewedSuite(
            wti=WTIStressEconomics(
                self.evidence,
                WTIStressAssumptions.from_ledger(self.assumptions, self.evidence),
            ),
            gold=GoldFalsificationEconomics(
                self.evidence,
                GoldStressAssumptions.from_ledger(self.assumptions),
            ),
            natural_gas=NaturalGasEvidenceReview(self.evidence),
        )
