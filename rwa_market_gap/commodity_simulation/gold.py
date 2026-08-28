"""Tokenized-gold structural falsification with size-dependent liquidity impact."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .common import EconomicLedger, UnsupportedModel, finite, non_negative, rate
from .evidence import VerifiedInputLedger
from .execution import PowerLawAverageImpactCurve


@dataclass(frozen=True)
class GoldStressAssumptions:
    requested_borrow_usd: float
    acquisition_fee_rate: float
    borrow_interest_rate_over_horizon: float
    gas_and_operations_usd: float
    impact_exponent: float

    def __post_init__(self) -> None:
        non_negative(self.requested_borrow_usd, "requested_borrow_usd")
        rate(self.acquisition_fee_rate, "acquisition_fee_rate")
        rate(
            self.borrow_interest_rate_over_horizon,
            "borrow_interest_rate_over_horizon",
        )
        non_negative(self.gas_and_operations_usd, "gas_and_operations_usd")
        if finite(self.impact_exponent, "impact_exponent") <= 0.0:
            raise ValueError("impact_exponent must be positive")

    @classmethod
    def from_ledger(cls, ledger: VerifiedInputLedger) -> "GoldStressAssumptions":
        prefix = "gold"
        return cls(
            requested_borrow_usd=float(
                ledger.value(f"{prefix}.requested_borrow_usd")
            ),
            acquisition_fee_rate=float(
                ledger.value(f"{prefix}.acquisition_fee_rate")
            ),
            borrow_interest_rate_over_horizon=float(
                ledger.value(f"{prefix}.borrow_interest_rate_over_horizon")
            ),
            gas_and_operations_usd=float(
                ledger.value(f"{prefix}.gas_and_operations_usd")
            ),
            impact_exponent=float(ledger.value(f"{prefix}.impact_exponent")),
        )


@dataclass(frozen=True)
class GoldFalsificationResult:
    snapshot_label: str
    tested_max_ltv: float
    max_ltv_source: str
    max_ltv_is_counterfactual: bool
    borrowed_usd: float
    collateral_oracle_value_usd: float
    collateral_tokens: float
    tested_discount_assumption: float
    tested_discount_source: str
    structural_zero_cost_break_even_discount: float
    modelled_break_even_discount: float
    reference_liquidity_utilization: float
    terminal_price_impact: float
    average_execution_slippage: float
    impact_exponent: float
    impact_observation_kind: str
    observed_liquidity_side: str
    modelled_execution_side: str
    uses_opposite_side_liquidity_proxy: bool
    liquidity_proxy_reason: str
    ledger: EconomicLedger
    profitable_at_tested_discount: bool
    success_probability: None = None
    probability_reason: str = (
        "The stale-oracle state is an explicit condition, not a calibrated random event."
    )


class GoldFalsificationEconomics:
    def __init__(
        self,
        evidence: VerifiedInputLedger,
        assumptions: GoldStressAssumptions,
    ) -> None:
        self.evidence = evidence
        self.assumptions = assumptions

    def with_impact_exponent(self, exponent: float) -> "GoldFalsificationEconomics":
        return GoldFalsificationEconomics(
            self.evidence,
            replace(self.assumptions, impact_exponent=exponent),
        )

    def analyze(
        self,
        *,
        token_discount: float | None = None,
        max_ltv: float | None = None,
        stale_oracle_available: bool = True,
    ) -> GoldFalsificationResult | UnsupportedModel:
        if not stale_oracle_available:
            return UnsupportedModel(
                name="gold stale-collateral attempt",
                reason=(
                    "Without a stale oracle, the supplied strategy has no defined "
                    "overvaluation step. Resale price risk is not fabricated."
                ),
                required_evidence=(
                    "time-aligned token resale path",
                    "transaction-level oracle and borrow timing",
                ),
            )
        prefix = "gold_collateral"
        published_ltv = float(self.evidence.value(f"{prefix}.max_ltv"))
        ltv = published_ltv if max_ltv is None else rate(max_ltv, "max_ltv")
        if ltv <= 0.0:
            raise ValueError("max_ltv must be positive")
        max_ltv_source = (
            self.evidence.record(f"{prefix}.max_ltv").source
            if max_ltv is None
            else "caller-supplied counterfactual max-LTV comparison"
        )
        debt_cap = float(self.evidence.value(f"{prefix}.debt_cap_usd"))
        uses_observed_divergence = token_discount is None
        tested_discount = float(
            self.evidence.value(f"{prefix}.observed_max_token_metal_divergence")
            if token_discount is None
            else token_discount
        )
        rate(tested_discount, "token_discount")
        tested_discount_source = (
            "maximum observed token-to-metal divergence applied as an "
            "attacker-favorable discount assumption"
            if uses_observed_divergence
            else "caller-supplied discount assumption"
        )
        borrowed = min(self.assumptions.requested_borrow_usd, debt_cap)
        collateral_face = borrowed / ltv

        reference_capacity_usd = float(
            self.evidence.value(f"{prefix}.disposal_capacity_within_bonus_usd")
        )
        reference_capacity_tokens = float(
            self.evidence.value(f"{prefix}.disposal_capacity_within_bonus_tokens")
        )
        snapshot_token_price = (
            reference_capacity_usd / reference_capacity_tokens
        )
        collateral_tokens = collateral_face / snapshot_token_price
        curve = PowerLawAverageImpactCurve(
            reference_quantity=reference_capacity_tokens,
            average_impact_at_reference=float(
                self.evidence.value(
                    f"{prefix}.disposal_capacity_average_price_impact_bound"
                )
            ),
            exponent=self.assumptions.impact_exponent,
        )
        terminal_impact = curve.terminal_impact(collateral_tokens)
        average_slippage = curve.average_slippage(collateral_tokens)

        market_purchase_value = collateral_face * (1.0 - tested_discount)
        slippage_cost = market_purchase_value * average_slippage
        fee = collateral_face * self.assumptions.acquisition_fee_rate
        interest = borrowed * self.assumptions.borrow_interest_rate_over_horizon
        acquisition_coc = (
            market_purchase_value
            + slippage_cost
            + fee
            + interest
            + self.assumptions.gas_and_operations_usd
        )
        ledger = EconomicLedger(
            pfc_usd=borrowed,
            coc_usd=acquisition_coc,
            capital_at_risk_usd=(
                market_purchase_value
                + slippage_cost
                + fee
                + self.assumptions.gas_and_operations_usd
            ),
        )
        break_even = 1.0 - (
            borrowed - fee - interest - self.assumptions.gas_and_operations_usd
        ) / (collateral_face * (1.0 + average_slippage))
        return GoldFalsificationResult(
            snapshot_label=(
                "historical listing-package analysis: June 2025 liquidity and "
                "August 2025 proposed risk parameters; not current state"
            ),
            tested_max_ltv=ltv,
            max_ltv_source=max_ltv_source,
            max_ltv_is_counterfactual=max_ltv is not None,
            borrowed_usd=borrowed,
            collateral_oracle_value_usd=collateral_face,
            collateral_tokens=collateral_tokens,
            tested_discount_assumption=tested_discount,
            tested_discount_source=tested_discount_source,
            structural_zero_cost_break_even_discount=1.0 - ltv,
            modelled_break_even_discount=break_even,
            reference_liquidity_utilization=(
                collateral_tokens / reference_capacity_tokens
            ),
            terminal_price_impact=terminal_impact,
            average_execution_slippage=average_slippage,
            impact_exponent=self.assumptions.impact_exponent,
            impact_observation_kind=(
                "upper bound used as an average execution-impact proxy"
            ),
            observed_liquidity_side="sell XAUt for USDC",
            modelled_execution_side="buy XAUt collateral",
            uses_opposite_side_liquidity_proxy=True,
            liquidity_proxy_reason=(
                "Only a sell-side disposal-depth bound was supplied. The bound "
                "is used as a conservative average-impact proxy for buy-side "
                "acquisition cost; side symmetry is not established."
            ),
            ledger=ledger,
            profitable_at_tested_discount=ledger.profitable,
        )

    def minimum_ltv_for_discount(
        self,
        token_discount: float,
        *,
        tolerance: float = 1e-10,
        max_iterations: int = 200,
    ) -> float | None:
        """Return the max LTV where the supplied discount first breaks even.

        This is a deterministic threshold, not a recommended risk parameter.
        It keeps every other model input fixed and varies only max LTV. ``None``
        means that even an LTV arbitrarily close to 100% does not break even.
        """

        discount = rate(token_discount, "token_discount")
        if tolerance <= 0.0:
            raise ValueError("tolerance must be positive")
        if max_iterations <= 0:
            raise ValueError("max_iterations must be positive")

        low = 1e-9
        high = 1.0 - 1e-9
        high_result = self.analyze(token_discount=discount, max_ltv=high)
        if not isinstance(high_result, GoldFalsificationResult):
            raise AssertionError("the supplied stale state should be executable")
        if high_result.ledger.net_profit_usd < 0.0:
            return None

        for _ in range(max_iterations):
            midpoint = (low + high) / 2.0
            result = self.analyze(token_discount=discount, max_ltv=midpoint)
            if not isinstance(result, GoldFalsificationResult):
                raise AssertionError("the supplied stale state should be executable")
            if result.ledger.net_profit_usd >= 0.0:
                high = midpoint
            else:
                low = midpoint
            if high - low <= tolerance:
                break
        return high
