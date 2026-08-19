"""Facade for the public commodity simulation package."""

from __future__ import annotations

from dataclasses import dataclass

from .evidence import VerifiedInputLedger
from .gold import GoldFalsificationEconomics, GoldStressAssumptions
from .inputs import load_assumptions
from .market_mechanics import (
    BandIdentityRow,
    LeverageZone,
    MarketSpec,
    band_identity_report,
    leverage_zone,
    market_specs,
)
from .natural_gas import NaturalGasEvidenceReview
from .wti import WTIStressAssumptions, WTIStressEconomics


@dataclass(frozen=True)
class CommoditySimulationSuite:
    wti: WTIStressEconomics
    gold: GoldFalsificationEconomics
    natural_gas: NaturalGasEvidenceReview


class CommoditySimulationEngine:
    def __init__(
        self,
        evidence: VerifiedInputLedger | None = None,
        assumptions: VerifiedInputLedger | None = None,
    ) -> None:
        self.evidence = evidence or VerifiedInputLedger.load()
        self.assumptions = assumptions or load_assumptions()
        self.evidence.assert_complete()
        self.assumptions.assert_complete()

    def build(self) -> CommoditySimulationSuite:
        return CommoditySimulationSuite(
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

    # Published-parameter mechanics. These carry no cost assumption and no
    # attacker model, so they are exposed separately from the stress models.

    def market_specs(self) -> tuple[MarketSpec, ...]:
        return market_specs(self.evidence)

    def band_identity(self) -> tuple[BandIdentityRow, ...]:
        return band_identity_report(self.evidence)

    def leverage_zone(self, symbol: str, chosen_leverage: float) -> LeverageZone:
        return leverage_zone(self.evidence, symbol, chosen_leverage)
