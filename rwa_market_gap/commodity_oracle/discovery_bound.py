"""Path-dependent discovery-bound and oracle update-clamp mechanics."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Iterable, Literal


Direction = Literal["up", "down", "none"]


@dataclass(frozen=True)
class BoundStep:
    raw_price: float
    effective_mark_price: float
    reference_before: float
    reference_after: float
    upward_resets_used: int
    downward_resets_used: int
    trigger_direction: Direction


class DiscoveryBoundMachine:
    """Stateful discovery bound with independent directional reset budgets.

    This follows the sequential state machine in the supplied validation
    guide. It intentionally does not collapse the path into a final hard cap.
    Per-update relayer clamping is modelled separately by
    :class:`OracleUpdateClamp`.
    """

    def __init__(
        self,
        *,
        reference_price: float,
        band_rate: float,
        reset_limit: int,
        trigger_fraction: float = 0.90,
    ) -> None:
        if reference_price <= 0.0:
            raise ValueError("reference_price must be positive")
        if not 0.0 < band_rate < 1.0:
            raise ValueError("band_rate must be in (0, 1)")
        if reset_limit < 0:
            raise ValueError("reset_limit must be non-negative")
        if not 0.0 < trigger_fraction <= 1.0:
            raise ValueError("trigger_fraction must be in (0, 1]")
        self.initial_reference_price = reference_price
        self.reference_price = reference_price
        self.band_rate = band_rate
        self.reset_limit = reset_limit
        self.trigger_fraction = trigger_fraction
        self.upward_resets_used = 0
        self.downward_resets_used = 0
        self.last_mark_price = reference_price

    @property
    def lower_bound(self) -> float:
        return self.reference_price * (1.0 - self.band_rate)

    @property
    def upper_bound(self) -> float:
        return self.reference_price * (1.0 + self.band_rate)

    def step(self, raw_price: float) -> BoundStep:
        if raw_price <= 0.0:
            raise ValueError("raw_price must be positive")
        reference_before = self.reference_price
        lower = self.lower_bound
        upper = self.upper_bound
        effective = min(max(raw_price, lower), upper)
        direction: Direction = "none"

        upward_trigger = reference_before * (
            1.0 + self.band_rate * self.trigger_fraction
        )
        downward_trigger = reference_before * (
            1.0 - self.band_rate * self.trigger_fraction
        )
        if (
            effective >= upward_trigger
            and self.upward_resets_used < self.reset_limit
        ):
            self.reference_price = upper
            self.upward_resets_used += 1
            direction = "up"
        elif (
            effective <= downward_trigger
            and self.downward_resets_used < self.reset_limit
        ):
            self.reference_price = lower
            self.downward_resets_used += 1
            direction = "down"

        self.last_mark_price = effective
        return BoundStep(
            raw_price=raw_price,
            effective_mark_price=effective,
            reference_before=reference_before,
            reference_after=self.reference_price,
            upward_resets_used=self.upward_resets_used,
            downward_resets_used=self.downward_resets_used,
            trigger_direction=direction,
        )

    def process(self, prices: Iterable[float]) -> tuple[BoundStep, ...]:
        return tuple(self.step(price) for price in prices)

    def reset_for_external_session(self, live_external_price: float) -> None:
        """Re-anchor to the live external session and clear both counters."""

        if live_external_price <= 0.0:
            raise ValueError("live_external_price must be positive")
        self.initial_reference_price = live_external_price
        self.reference_price = live_external_price
        self.last_mark_price = live_external_price
        self.upward_resets_used = 0
        self.downward_resets_used = 0

    def theoretical_hard_cap(self, direction: Literal["up", "down"]) -> float:
        multiplier = 1.0 + self.band_rate if direction == "up" else 1.0 - self.band_rate
        return self.initial_reference_price * multiplier ** (self.reset_limit + 1)


@dataclass(frozen=True)
class OracleUpdateClamp:
    """The binding of protocol-level and relayer-level update clamps."""

    protocol_rate: float
    relayer_rate: float

    def __post_init__(self) -> None:
        for name, rate in (
            ("protocol_rate", self.protocol_rate),
            ("relayer_rate", self.relayer_rate),
        ):
            if not 0.0 < rate < 1.0:
                raise ValueError(f"{name} must be in (0, 1)")

    @property
    def binding_rate(self) -> float:
        return min(self.protocol_rate, self.relayer_rate)

    def apply_once(self, current: float, target: float) -> float:
        if current <= 0.0 or target <= 0.0:
            raise ValueError("prices must be positive")
        upper = current * (1.0 + self.binding_rate)
        lower = current * (1.0 - self.binding_rate)
        return min(max(target, lower), upper)

    def minimum_updates_for_reference_gap(self, gap_rate: float) -> int:
        """Lower bound used by the validation guide for a gap in percentage points."""

        return ceil(abs(gap_rate) / self.binding_rate)
