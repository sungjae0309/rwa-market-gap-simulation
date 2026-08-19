"""Shared, finite-only accounting types for the commodity simulation."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


def finite(value: float, name: str) -> float:
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def non_negative(value: float, name: str) -> float:
    number = finite(value, name)
    if number < 0.0:
        raise ValueError(f"{name} must be non-negative")
    return number


def rate(value: float, name: str, *, signed: bool = False) -> float:
    number = finite(value, name)
    low = -1.0 if signed else 0.0
    if not low <= number <= 1.0:
        interval = "[-1, 1]" if signed else "[0, 1]"
        raise ValueError(f"{name} must be in {interval}")
    return number


@dataclass(frozen=True)
class EconomicLedger:
    """Realized cash-flow accounting for one explicitly defined state."""

    pfc_usd: float
    coc_usd: float
    capital_at_risk_usd: float

    def __post_init__(self) -> None:
        non_negative(self.pfc_usd, "pfc_usd")
        non_negative(self.coc_usd, "coc_usd")
        non_negative(self.capital_at_risk_usd, "capital_at_risk_usd")

    @property
    def net_profit_usd(self) -> float:
        return self.pfc_usd - self.coc_usd

    @property
    def profitable(self) -> bool:
        return self.net_profit_usd > 0.0


@dataclass(frozen=True)
class UnsupportedModel:
    name: str
    reason: str
    required_evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.reason.strip():
            raise ValueError("unsupported-model name and reason must not be blank")
        if not self.required_evidence or any(
            not item.strip() for item in self.required_evidence
        ):
            raise ValueError("required_evidence must contain non-blank items")
