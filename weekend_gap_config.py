"""Configuration for the deterministic weekend market-gap baseline."""

from __future__ import annotations

from dataclasses import dataclass


def _require_non_negative(name: str, value: float) -> None:
    if value < 0:
        raise ValueError(f"{name} must be non-negative, got {value}")


def _require_probability(name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be in [0, 1], got {value}")


@dataclass(frozen=True)
class WeekendGapConfig:
    """Weekend price-gap and strategic-default assumptions.

    Defaults reproduce an illustrative research example. They are not
    verified live-market or protocol parameters.
    """

    collateral_value_usd: float = 1_000_000.0
    ltv: float = 0.70
    liquidation_threshold: float = 0.80
    liquidation_bonus: float = 0.05
    closure_hours: float = 48.0
    annual_borrow_rate: float = 0.06
    transaction_cost_usd: float = 200.0
    onchain_pool_depth_usd: float = 3_000_000.0
    new_borrowing_enabled: bool = True

    def __post_init__(self) -> None:
        _require_non_negative("collateral_value_usd", self.collateral_value_usd)
        _require_probability("ltv", self.ltv)
        if not 0.0 < self.liquidation_threshold <= 1.0:
            raise ValueError("liquidation_threshold must be in (0, 1]")
        if self.ltv > self.liquidation_threshold:
            raise ValueError("ltv must not exceed liquidation_threshold")
        _require_non_negative("liquidation_bonus", self.liquidation_bonus)
        _require_non_negative("closure_hours", self.closure_hours)
        _require_non_negative("annual_borrow_rate", self.annual_borrow_rate)
        _require_non_negative("transaction_cost_usd", self.transaction_cost_usd)
        _require_non_negative(
            "onchain_pool_depth_usd", self.onchain_pool_depth_usd
        )
        if not isinstance(self.new_borrowing_enabled, bool):
            raise TypeError("new_borrowing_enabled must be a boolean")
