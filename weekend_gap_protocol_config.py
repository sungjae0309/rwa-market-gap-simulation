"""Configuration for the protocol-aware Weekend Gap research model.

This module intentionally lives beside, rather than replaces,
``weekend_gap_config.WeekendGapConfig``. Its defaults are conservative and
unverified: a closed-market loan is blocked until the researcher explicitly
supplies the target protocol's oracle policy and enables that path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


MarketStatus = Literal["open", "closed", "halted", "unknown"]


def _require_finite_non_negative(name: str, value: float) -> None:
    if value < 0.0 or value == float("inf") or value != value:
        raise ValueError(f"{name} must be a finite non-negative number, got {value}")


def _require_positive(name: str, value: float) -> None:
    if value <= 0.0 or value == float("inf") or value != value:
        raise ValueError(f"{name} must be a finite positive number, got {value}")


def _require_probability(name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be in [0, 1], got {value}")


@dataclass(frozen=True)
class EvidenceConfig:
    """Tracks whether the inputs came from reproducible evidence.

    Setting these flags does not change any payoff.  They prevent an
    illustrative run from being accidentally described as an empirical
    protocol result.
    """

    protocol_parameters_verified: bool = False
    oracle_policy_verified: bool = False
    liquidity_snapshot_verified: bool = False
    gap_dataset_verified: bool = False
    source_notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        flags = (
            self.protocol_parameters_verified,
            self.oracle_policy_verified,
            self.liquidity_snapshot_verified,
            self.gap_dataset_verified,
        )
        if any(flags) and not self.source_notes:
            raise ValueError("verified evidence flags require at least one source note")
        if any(not isinstance(flag, bool) for flag in flags):
            raise TypeError("evidence flags must be booleans")

    @property
    def protocol_inputs_verified(self) -> bool:
        return (
            self.protocol_parameters_verified
            and self.oracle_policy_verified
            and self.liquidity_snapshot_verified
        )

    @property
    def fully_verified(self) -> bool:
        return self.protocol_inputs_verified and self.gap_dataset_verified


@dataclass(frozen=True)
class OracleGuardConfig:
    """Closed-market, freshness, and price-band rules for loan origination."""

    market_status: MarketStatus = "closed"
    last_close_price_usd: float = 100.0
    oracle_price_usd: float = 100.0
    feed_age_seconds: float = 48.0 * 60.0 * 60.0
    max_feed_age_for_new_loan_seconds: float = 60.0
    allow_new_loans_when_market_closed: bool = False
    closed_market_staleness_exemption: bool = False
    closed_market_price_band_rate: float = 0.05

    def __post_init__(self) -> None:
        if self.market_status not in {"open", "closed", "halted", "unknown"}:
            raise ValueError(f"unsupported market_status: {self.market_status}")
        _require_positive("last_close_price_usd", self.last_close_price_usd)
        _require_positive("oracle_price_usd", self.oracle_price_usd)
        _require_finite_non_negative("feed_age_seconds", self.feed_age_seconds)
        _require_finite_non_negative(
            "max_feed_age_for_new_loan_seconds",
            self.max_feed_age_for_new_loan_seconds,
        )
        _require_probability(
            "closed_market_price_band_rate", self.closed_market_price_band_rate
        )
        if not isinstance(self.allow_new_loans_when_market_closed, bool):
            raise TypeError("allow_new_loans_when_market_closed must be a boolean")
        if not isinstance(self.closed_market_staleness_exemption, bool):
            raise TypeError("closed_market_staleness_exemption must be a boolean")

    @property
    def deviation_from_last_close(self) -> float:
        return abs(self.oracle_price_usd / self.last_close_price_usd - 1.0)


@dataclass(frozen=True)
class LendingReserveConfig:
    """Protocol reserve snapshot used to size the weekend loan."""

    collateral_amount_units: float = 10_000.0
    max_ltv: float = 0.70
    liquidation_ltv: float = 0.80
    debt_borrow_factor: float = 1.0
    collateral_supply_cap_usd: float = 20_000_000.0
    collateral_supplied_before_attack_usd: float = 5_000_000.0
    debt_reserve_total_supply_usd: float = 20_000_000.0
    debt_reserve_current_borrowed_usd: float = 10_000_000.0
    debt_borrow_cap_usd: float = 20_000_000.0
    new_loans_allowed: bool = True

    def __post_init__(self) -> None:
        _require_finite_non_negative(
            "collateral_amount_units", self.collateral_amount_units
        )
        _require_probability("max_ltv", self.max_ltv)
        if not 0.0 < self.liquidation_ltv <= 1.0:
            raise ValueError("liquidation_ltv must be in (0, 1]")
        if self.max_ltv > self.liquidation_ltv:
            raise ValueError("max_ltv must not exceed liquidation_ltv")
        if self.debt_borrow_factor < 1.0:
            raise ValueError("debt_borrow_factor must be at least 1")
        for name in (
            "collateral_supply_cap_usd",
            "collateral_supplied_before_attack_usd",
            "debt_reserve_total_supply_usd",
            "debt_reserve_current_borrowed_usd",
            "debt_borrow_cap_usd",
        ):
            _require_finite_non_negative(name, getattr(self, name))
        if self.collateral_supplied_before_attack_usd > self.collateral_supply_cap_usd:
            raise ValueError("existing collateral supply exceeds its cap")
        if self.debt_reserve_current_borrowed_usd > self.debt_reserve_total_supply_usd:
            raise ValueError("current debt exceeds supplied debt liquidity")
        if self.debt_reserve_current_borrowed_usd > self.debt_borrow_cap_usd:
            raise ValueError("current debt exceeds the debt borrow cap")
        if not isinstance(self.new_loans_allowed, bool):
            raise TypeError("new_loans_allowed must be a boolean")


@dataclass(frozen=True)
class InterestRateCurveConfig:
    """Piecewise-linear utilization curve plus a position risk premium."""

    base_rate: float = 0.02
    kink_utilization: float = 0.80
    rate_at_kink: float = 0.10
    maximum_rate: float = 1.00
    position_risk_premium: float = 0.0

    def __post_init__(self) -> None:
        _require_finite_non_negative("base_rate", self.base_rate)
        if not 0.0 < self.kink_utilization < 1.0:
            raise ValueError("kink_utilization must be in (0, 1)")
        _require_finite_non_negative("rate_at_kink", self.rate_at_kink)
        _require_finite_non_negative("maximum_rate", self.maximum_rate)
        _require_finite_non_negative(
            "position_risk_premium", self.position_risk_premium
        )
        if self.base_rate > self.rate_at_kink:
            raise ValueError("base_rate must not exceed rate_at_kink")
        if self.rate_at_kink > self.maximum_rate:
            raise ValueError("rate_at_kink must not exceed maximum_rate")


@dataclass(frozen=True)
class LiquidationMechanismConfig:
    """Iterative close-factor liquidation with a time-varying bonus."""

    close_factor: float = 0.10
    minimum_bonus: float = 0.001
    maximum_bonus: float = 0.10
    bonus_ramp_hours: float = 24.0
    round_interval_seconds: float = 12.0
    maximum_simulation_hours: float = 2.0
    max_debt_repaid_per_round_usd: float = 1_000_000.0
    collateral_sale_slippage_rate: float = 0.002
    execution_cost_per_round_usd: float = 5.0
    minimum_liquidator_profit_usd: float = 0.0

    def __post_init__(self) -> None:
        if not 0.0 < self.close_factor <= 1.0:
            raise ValueError("close_factor must be in (0, 1]")
        _require_probability("minimum_bonus", self.minimum_bonus)
        _require_probability("maximum_bonus", self.maximum_bonus)
        if self.minimum_bonus > self.maximum_bonus:
            raise ValueError("minimum_bonus must not exceed maximum_bonus")
        _require_finite_non_negative("bonus_ramp_hours", self.bonus_ramp_hours)
        _require_positive("round_interval_seconds", self.round_interval_seconds)
        _require_finite_non_negative(
            "maximum_simulation_hours", self.maximum_simulation_hours
        )
        _require_positive(
            "max_debt_repaid_per_round_usd",
            self.max_debt_repaid_per_round_usd,
        )
        _require_probability(
            "collateral_sale_slippage_rate",
            self.collateral_sale_slippage_rate,
        )
        _require_finite_non_negative(
            "execution_cost_per_round_usd", self.execution_cost_per_round_usd
        )
        _require_finite_non_negative(
            "minimum_liquidator_profit_usd",
            self.minimum_liquidator_profit_usd,
        )


@dataclass(frozen=True)
class OnchainLiquidityConfig:
    """Either a captured aggregator quote or an explicit constant-product pool."""

    asset_reserve_units: float = 30_000.0
    stable_reserve_usd: float = 3_000_000.0
    swap_fee_rate: float = 0.003
    aggregator_quote_for_full_position_usd: float | None = None
    quote_label: str = "illustrative constant-product pool"

    def __post_init__(self) -> None:
        _require_positive("asset_reserve_units", self.asset_reserve_units)
        _require_positive("stable_reserve_usd", self.stable_reserve_usd)
        _require_probability("swap_fee_rate", self.swap_fee_rate)
        if self.aggregator_quote_for_full_position_usd is not None:
            _require_finite_non_negative(
                "aggregator_quote_for_full_position_usd",
                self.aggregator_quote_for_full_position_usd,
            )
        if not self.quote_label.strip():
            raise ValueError("quote_label must not be blank")


@dataclass(frozen=True)
class AttackExecutionConfig:
    """Attacker settlement, exit, and directly paid cost assumptions."""

    closure_hours: float = 48.0
    origination_transaction_cost_usd: float = 100.0
    repayment_transaction_cost_usd: float = 100.0
    annual_collateral_financing_rate: float = 0.0
    non_recourse_default: bool = True
    borrowed_cash_exit_recovery_rate: float = 1.0

    def __post_init__(self) -> None:
        _require_finite_non_negative("closure_hours", self.closure_hours)
        _require_finite_non_negative(
            "origination_transaction_cost_usd",
            self.origination_transaction_cost_usd,
        )
        _require_finite_non_negative(
            "repayment_transaction_cost_usd",
            self.repayment_transaction_cost_usd,
        )
        _require_finite_non_negative(
            "annual_collateral_financing_rate",
            self.annual_collateral_financing_rate,
        )
        _require_probability(
            "borrowed_cash_exit_recovery_rate",
            self.borrowed_cash_exit_recovery_rate,
        )
        if not isinstance(self.non_recourse_default, bool):
            raise TypeError("non_recourse_default must be a boolean")


@dataclass(frozen=True)
class ProtocolAwareWeekendGapConfig:
    """Dependency-injection object for the separate protocol-aware model."""

    protocol_name: str = "UNVERIFIED_PROTOCOL"
    collateral_symbol: str = "UNVERIFIED_XSTOCK"
    snapshot_label: str = "illustrative defaults - not a live snapshot"
    evidence: EvidenceConfig = field(default_factory=EvidenceConfig)
    oracle: OracleGuardConfig = field(default_factory=OracleGuardConfig)
    reserve: LendingReserveConfig = field(default_factory=LendingReserveConfig)
    interest_curve: InterestRateCurveConfig = field(
        default_factory=InterestRateCurveConfig
    )
    liquidation: LiquidationMechanismConfig = field(
        default_factory=LiquidationMechanismConfig
    )
    liquidity: OnchainLiquidityConfig = field(default_factory=OnchainLiquidityConfig)
    attack: AttackExecutionConfig = field(default_factory=AttackExecutionConfig)

    def __post_init__(self) -> None:
        if not self.protocol_name.strip():
            raise ValueError("protocol_name must not be blank")
        if not self.collateral_symbol.strip():
            raise ValueError("collateral_symbol must not be blank")
        if not self.snapshot_label.strip():
            raise ValueError("snapshot_label must not be blank")


DEFAULT_PROTOCOL_AWARE_WEEKEND_GAP_CONFIG = ProtocolAwareWeekendGapConfig()
