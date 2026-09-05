"""WTI stress-event economics without a fabricated success probability."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isclose

from .common import EconomicLedger, UnsupportedModel, finite, non_negative, rate
from .evidence import VerifiedInputLedger
from .execution import CapacityResult, apply_capacity


@dataclass(frozen=True)
class WTIStressAssumptions:
    """Declared WTI strategy inputs; capacity and costs are not observed fills."""

    requested_notional_usd: float  # Position size requested by the strategy.
    assumed_capacity_usd: float  # Unverified executable-notional ceiling.
    allocated_margin_usd: float  # Capital allocated as margin, not full account equity.
    round_trip_fee_rate: float
    round_trip_slippage_rate: float  # Slippage at the capacity reference point.
    slippage_exponent: float  # Curvature of size-dependent slippage.
    signed_funding_rate_over_horizon: float
    funding_sensitivity_low: float
    funding_sensitivity_high: float
    capital_annual_rate: float
    horizon_hours: float  # Holding window; 49 hours for the standard CME weekend.

    def __post_init__(self) -> None:
        non_negative(self.requested_notional_usd, "requested_notional_usd")
        non_negative(self.assumed_capacity_usd, "assumed_capacity_usd")
        if finite(self.allocated_margin_usd, "allocated_margin_usd") <= 0.0:
            raise ValueError("allocated_margin_usd must be positive")
        rate(self.round_trip_fee_rate, "round_trip_fee_rate")
        rate(self.round_trip_slippage_rate, "round_trip_slippage_rate")
        if finite(self.slippage_exponent, "slippage_exponent") <= 0.0:
            raise ValueError("slippage_exponent must be positive")
        rate(
            self.signed_funding_rate_over_horizon,
            "signed_funding_rate_over_horizon",
            signed=True,
        )
        low = rate(
            self.funding_sensitivity_low,
            "funding_sensitivity_low",
            signed=True,
        )
        high = rate(
            self.funding_sensitivity_high,
            "funding_sensitivity_high",
            signed=True,
        )
        if low > high:
            raise ValueError("funding sensitivity lower bound exceeds upper bound")
        if not low <= self.signed_funding_rate_over_horizon <= high:
            raise ValueError("assumed funding must lie inside its sensitivity range")
        rate(self.capital_annual_rate, "capital_annual_rate")
        if finite(self.horizon_hours, "horizon_hours") <= 0.0:
            raise ValueError("horizon_hours must be positive")

    @classmethod
    def from_ledger(
        cls, ledger: VerifiedInputLedger, evidence: VerifiedInputLedger
    ) -> "WTIStressAssumptions":
        prefix = "wti"
        funding_record = ledger.record(
            f"{prefix}.signed_funding_rate_over_horizon"
        )
        if funding_record.sensitivity is None:
            raise ValueError("WTI funding assumption requires sensitivity bounds")
        funding_low, funding_high = funding_record.sensitivity
        return cls(
            # The closure length is a published session fact, not a modelling
            # choice, so it is read as grade-A evidence rather than defaulted in
            # code or inherited from the original attack-economics model.
            horizon_hours=float(
                evidence.value("market_sessions.standard_weekend_closure_hours")
            ),
            requested_notional_usd=float(
                ledger.value(f"{prefix}.requested_notional_usd")
            ),
            assumed_capacity_usd=float(
                ledger.value(f"{prefix}.assumed_capacity_usd")
            ),
            allocated_margin_usd=float(
                ledger.value(f"{prefix}.allocated_margin_usd")
            ),
            round_trip_fee_rate=float(
                ledger.value(f"{prefix}.round_trip_fee_rate")
            ),
            round_trip_slippage_rate=float(
                ledger.value(f"{prefix}.round_trip_slippage_rate")
            ),
            slippage_exponent=float(
                ledger.value(f"{prefix}.slippage_exponent")
            ),
            signed_funding_rate_over_horizon=float(
                funding_record.value
            ),
            funding_sensitivity_low=funding_low,
            funding_sensitivity_high=funding_high,
            capital_annual_rate=float(
                ledger.value(f"{prefix}.capital_annual_rate")
            ),
        )


@dataclass(frozen=True)
class WTIStressResult:
    event: str
    friday_close_usd: float
    onchain_entry_mark_usd: float
    external_reopen_usd: float
    position_direction: str
    signed_price_recognition_gap_rate: float
    price_recognition_gap_rate: float
    position_return_rate: float
    capacity: CapacityResult
    effective_leverage: float
    ledger: EconomicLedger
    realized_round_trip_slippage_rate: float
    break_even_positive_return_rate: float
    assumed_funding_rate_over_horizon: float
    break_even_funding_rate_over_horizon: float
    simple_average_break_even_funding_rate_per_hour: float
    holding_horizon_hours: float
    funding_sensitivity_low: float
    funding_sensitivity_high: float
    break_even_funding_within_declared_sensitivity: bool
    direction_match_observation: float
    success_probability: None = None
    probability_reason: str = (
        "No unconditional WTI gap distribution was supplied; the 89.9% study "
        "observation is metadata, not a simulated success probability."
    )

    @property
    def break_even_funding_rate_per_hour(self) -> float:
        """Backward-compatible alias; this is only a simple hourly average."""

        return self.simple_average_break_even_funding_rate_per_hour


class WTIStressEconomics:
    def __init__(
        self,
        evidence: VerifiedInputLedger,
        assumptions: WTIStressAssumptions,
    ) -> None:
        self.evidence = evidence
        self.assumptions = assumptions

    def with_requested_notional(self, requested_usd: float) -> "WTIStressEconomics":
        return WTIStressEconomics(
            self.evidence,
            replace(self.assumptions, requested_notional_usd=requested_usd),
        )

    def analyze(self, event: str) -> WTIStressResult:
        if event not in {"wti_first_weekend", "wti_second_weekend"}:
            raise ValueError("unsupported WTI stress event")
        prefix = f"events.{event}"
        close = float(self.evidence.value(f"{prefix}.friday_cme_close_usd"))
        mark = float(self.evidence.value(f"{prefix}.observed_onchain_mark_usd"))
        reopen = float(self.evidence.value(f"{prefix}.cme_reopen_price_usd"))
        result = self.analyze_prices(
            event=event,
            friday_close_usd=close,
            onchain_entry_mark_usd=mark,
            external_reopen_usd=reopen,
        )
        if isinstance(result, UnsupportedModel):
            raise ValueError(f"{event} is not supported: {result.reason}")
        return result

    def analyze_prices(
        self,
        *,
        event: str,
        friday_close_usd: float,
        onchain_entry_mark_usd: float,
        external_reopen_usd: float,
    ) -> WTIStressResult | UnsupportedModel:
        close = finite(friday_close_usd, "friday_close_usd")
        mark = finite(onchain_entry_mark_usd, "onchain_entry_mark_usd")
        reopen = finite(external_reopen_usd, "external_reopen_usd")
        if min(close, mark, reopen) <= 0.0:
            raise ValueError("WTI prices must be positive")
        if isclose(mark, close, rel_tol=0.0, abs_tol=1e-12):
            return UnsupportedModel(
                name=f"{event} WTI directional strategy",
                reason=(
                    "The onchain mark equals the external close, so the supplied "
                    "direction rule produces no trading signal."
                ),
                required_evidence=("a separate entry-direction rule",),
            )
        # Follow the observed onchain mark direction relative to the Friday close.
        direction = 1.0 if mark > close else -1.0
        direction_name = "long" if direction > 0.0 else "short"
        signed_recognition_gap = (reopen - mark) / close
        recognition_gap = abs(signed_recognition_gap)
        position_return = direction * (reopen - mark) / mark
        if position_return <= 0.0:
            return UnsupportedModel(
                name=f"{event} WTI adverse execution path",
                reason=(
                    "The supplied model has no event order book or "
                    "liquidation timeline. It therefore does not fabricate a "
                    "threshold fill, backstop loss, or ADL outcome."
                ),
                required_evidence=(
                    "time-aligned adverse WTI event",
                    "entry-to-liquidation order-book path",
                    "position close or liquidation timestamp",
                ),
            )

        capacity = apply_capacity(
            self.assumptions.requested_notional_usd,
            self.assumptions.assumed_capacity_usd,
        )
        notional = capacity.executable_notional_usd
        if notional <= 0.0:
            raise ValueError("WTI executable notional must be positive")
        allocated_margin = self.assumptions.allocated_margin_usd
        effective_leverage = notional / allocated_margin
        max_leverage = float(
            self.evidence.value("markets.WTIOIL.max_leverage")
        )
        if effective_leverage <= 0.0 or effective_leverage > max_leverage:
            raise ValueError(
                "WTI effective leverage must be in (0, published maximum]"
            )
        fee = notional * self.assumptions.round_trip_fee_rate
        # The configured rate is the average round-trip slippage at the
        # capacity reference point. Smaller orders scale non-linearly rather
        # than inheriting the same percentage cost at every size.
        capacity_utilization = notional / self.assumptions.assumed_capacity_usd
        realized_slippage_rate = self.assumptions.round_trip_slippage_rate * (
            capacity_utilization ** self.assumptions.slippage_exponent
        )
        slippage = notional * realized_slippage_rate
        funding_cashflow = (
            -notional * self.assumptions.signed_funding_rate_over_horizon
        )
        funding_receipt = max(0.0, funding_cashflow)
        funding_payment = max(0.0, -funding_cashflow)
        capital_cost = (
            allocated_margin
            * self.assumptions.capital_annual_rate
            * self.assumptions.horizon_hours
            / 8_760.0
        )
        realized_profit = notional * position_return

        direct_cost = fee + slippage + funding_payment + capital_cost
        ledger = EconomicLedger(
            pfc_usd=realized_profit + funding_receipt,
            coc_usd=direct_cost,
            capital_at_risk_usd=allocated_margin,
        )
        break_even = max(0.0, direct_cost - funding_receipt) / notional

        # Funding is the mechanism that prices a persistent perpetual basis, so
        # the interesting quantity is not the assumed funding cost but the level
        # at which this state stops paying. Substituting
        # ``funding_receipt - funding_payment == -notional * f`` into
        # ``net = PfC - CoC`` collapses every funding term into one signed
        # cashflow, and the remaining terms do not depend on ``f``:
        #
        #   net(f) = realized_profit
        #            - fee - slippage - capital_cost - notional * f
        #
        # so ``net(f) == 0`` has the closed form below. A negative result means
        # the state only breaks even if the attacker is *paid* funding.
        break_even_funding = (
            realized_profit - fee - slippage - capital_cost
        ) / notional
        return WTIStressResult(
            event=event,
            friday_close_usd=close,
            onchain_entry_mark_usd=mark,
            external_reopen_usd=reopen,
            position_direction=direction_name,
            signed_price_recognition_gap_rate=signed_recognition_gap,
            price_recognition_gap_rate=recognition_gap,
            position_return_rate=position_return,
            capacity=capacity,
            effective_leverage=effective_leverage,
            ledger=ledger,
            realized_round_trip_slippage_rate=realized_slippage_rate,
            break_even_positive_return_rate=break_even,
            assumed_funding_rate_over_horizon=(
                self.assumptions.signed_funding_rate_over_horizon
            ),
            break_even_funding_rate_over_horizon=break_even_funding,
            simple_average_break_even_funding_rate_per_hour=(
                break_even_funding / self.assumptions.horizon_hours
            ),
            holding_horizon_hours=self.assumptions.horizon_hours,
            funding_sensitivity_low=self.assumptions.funding_sensitivity_low,
            funding_sensitivity_high=self.assumptions.funding_sensitivity_high,
            break_even_funding_within_declared_sensitivity=(
                self.assumptions.funding_sensitivity_low
                <= break_even_funding
                <= self.assumptions.funding_sensitivity_high
            ),
            direction_match_observation=float(
                self.evidence.value(
                    "market_studies.weekend_direction_match_rate"
                )
            ),
        )

    def analyze_all(self) -> tuple[WTIStressResult, WTIStressResult]:
        return (
            self.analyze("wti_first_weekend"),
            self.analyze("wti_second_weekend"),
        )
