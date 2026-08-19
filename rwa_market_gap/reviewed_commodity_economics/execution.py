"""Capacity and size-dependent execution models with explicit assumptions."""

from __future__ import annotations

from dataclasses import dataclass

from .common import finite, non_negative, rate


@dataclass(frozen=True)
class CapacityResult:
    requested_notional_usd: float
    executable_notional_usd: float
    assumed_capacity_usd: float
    capacity_constrained: bool


def apply_capacity(requested_notional_usd: float, capacity_usd: float) -> CapacityResult:
    requested = non_negative(requested_notional_usd, "requested_notional_usd")
    capacity = non_negative(capacity_usd, "capacity_usd")
    executable = min(requested, capacity)
    return CapacityResult(
        requested_notional_usd=requested,
        executable_notional_usd=executable,
        assumed_capacity_usd=capacity,
        capacity_constrained=requested > capacity,
    )


@dataclass(frozen=True)
class PowerLawAverageImpactCurve:
    """Power-law execution curve calibrated to an average-impact quote.

    The supplied liquidity observation says that a reference quantity can be
    swapped "within" a stated price impact.  It does not identify the final
    unit's marginal impact or an exact realized average, so the stated bound is
    used as a conservative average-impact proxy at the reference quantity.
    ``exponent`` remains a C-grade shape assumption.
    """

    reference_quantity: float
    average_impact_at_reference: float
    exponent: float

    def __post_init__(self) -> None:
        if finite(self.reference_quantity, "reference_quantity") <= 0.0:
            raise ValueError("reference_quantity must be positive")
        rate(
            self.average_impact_at_reference,
            "average_impact_at_reference",
        )
        if finite(self.exponent, "exponent") <= 0.0:
            raise ValueError("exponent must be positive")

    def average_slippage(self, quantity: float) -> float:
        quantity = non_negative(quantity, "quantity")
        impact = self.average_impact_at_reference * (
            quantity / self.reference_quantity
        ) ** self.exponent
        if impact >= 1.0:
            raise ValueError("modelled average impact reaches or exceeds 100%")
        return impact

    def terminal_impact(self, quantity: float) -> float:
        """Implied terminal impact if marginal impact is power-law shaped."""

        terminal = self.average_slippage(quantity) * (self.exponent + 1.0)
        if terminal >= 1.0:
            raise ValueError("modelled terminal impact reaches or exceeds 100%")
        return terminal
