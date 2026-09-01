"""Published market mechanics: the band identity, hard caps, and margin zones.

This module reproduces the parts of the commodity scenario that rest only on
published venue parameters, with no cost assumption and no attacker model:

* the band identity ``band_rate == 1 / max_leverage``;
* the reanchor state machine and the hard cap it implies;
* the maintenance-margin and liquidation-trigger arithmetic that decides which
  leverage bands the discovery bound actually protects;
* the collateral scope implied by cross and isolated margin.

These are the strongest claims in the scenario because every input is grade-A
published data, so they are kept separate from the assumption-driven WTI, gold,
and natural-gas models.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

from .common import finite, rate
from .evidence import VerifiedInputLedger


Direction = Literal["up", "down", "none"]
MarginMode = Literal["cross", "isolated"]


def maintenance_margin_rate(
    max_leverage: float, maintenance_margin_fraction: float
) -> float:
    """Maintenance margin fixed from the market maximum, not chosen leverage."""

    if finite(max_leverage, "max_leverage") <= 0.0:
        raise ValueError("max_leverage must be positive")
    fraction = finite(maintenance_margin_fraction, "maintenance_margin_fraction")
    if not 0.0 < fraction <= 1.0:
        raise ValueError("maintenance_margin_fraction must be in (0, 1]")
    return fraction / max_leverage


def liquidation_adverse_move(
    *,
    chosen_leverage: float,
    max_leverage: float,
    maintenance_margin_fraction: float,
) -> float:
    """Adverse move that starts liquidation under the simplified base tier.

    Published margin tiers for the commodity markets were not supplied, so this
    is the base-tier approximation only. Large positions may liquidate earlier.
    """

    leverage = finite(chosen_leverage, "chosen_leverage")
    if leverage <= 0.0 or leverage > max_leverage:
        raise ValueError("chosen_leverage must be in (0, max_leverage]")
    return 1.0 / leverage - maintenance_margin_rate(
        max_leverage, maintenance_margin_fraction
    )


def liquidation_collateral_scope(margin_mode: MarginMode) -> tuple[str, ...]:
    """Collateral exposed to liquidation under the published margin mode.

    Margin mode determines the scope of collateral, not whether a backstop or
    ADL stage was available or used in a particular event. Those later stages
    require event-specific evidence and are intentionally not inferred here.
    """

    if margin_mode == "cross":
        return ("cross_positions", "cross_margin_balance")
    if margin_mode == "isolated":
        return ("isolated_position", "isolated_margin_balance")
    raise ValueError(f"unsupported margin mode: {margin_mode}")


@dataclass(frozen=True)
class MarketSpec:
    symbol: str
    feed: str
    max_leverage: float
    band_rate: float
    reset_limit: int
    margin_mode: MarginMode
    external_session: str

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not self.feed.strip():
            raise ValueError("symbol and feed must not be blank")
        if finite(self.max_leverage, "max_leverage") <= 0.0:
            raise ValueError("max_leverage must be positive")
        if not 0.0 < rate(self.band_rate, "band_rate") < 1.0:
            raise ValueError("band_rate must be in (0, 1)")
        if self.reset_limit < 0:
            raise ValueError("reset_limit must be non-negative")
        if self.margin_mode not in {"cross", "isolated"}:
            raise ValueError("margin_mode must be cross or isolated")
        if not self.external_session.strip():
            raise ValueError("external_session must not be blank")

    @property
    def band_identity_error(self) -> float:
        """``band_rate - 1 / max_leverage``; zero when the identity holds."""

        return self.band_rate - 1.0 / self.max_leverage

    @property
    def bankruptcy_move_at_max_leverage(self) -> float:
        """Adverse move that consumes the whole initial margin at max leverage."""

        return 1.0 / self.max_leverage

    @property
    def upward_hard_cap_rate(self) -> float:
        return (1.0 + self.band_rate) ** (self.reset_limit + 1) - 1.0

    @property
    def downward_hard_cap_rate(self) -> float:
        return 1.0 - (1.0 - self.band_rate) ** (self.reset_limit + 1)

    @property
    def hard_cap_to_bankruptcy_multiple(self) -> float:
        """How far the reanchor budget pushes the cap past the bankruptcy line."""

        return self.upward_hard_cap_rate / self.bankruptcy_move_at_max_leverage

    @property
    def liquidation_collateral_scope(self) -> tuple[str, ...]:
        return liquidation_collateral_scope(self.margin_mode)

    @classmethod
    def from_ledger(cls, ledger: VerifiedInputLedger, symbol: str) -> "MarketSpec":
        prefix = f"markets.{symbol}"
        return cls(
            symbol=symbol,
            feed=str(ledger.value(f"{prefix}.feed")),
            max_leverage=float(ledger.value(f"{prefix}.max_leverage")),
            band_rate=float(ledger.value(f"{prefix}.band_rate")),
            reset_limit=int(ledger.value(f"{prefix}.reset_limit")),
            margin_mode=str(ledger.value(f"{prefix}.margin_mode")),
            external_session=str(ledger.value(f"{prefix}.external_session")),
        )


def published_market_symbols(ledger: VerifiedInputLedger) -> tuple[str, ...]:
    markets = ledger.payload.get("markets")
    if not isinstance(markets, dict) or not markets:
        raise ValueError("evidence ledger contains no published markets")
    return tuple(sorted(markets))


def market_specs(ledger: VerifiedInputLedger) -> tuple[MarketSpec, ...]:
    return tuple(
        MarketSpec.from_ledger(ledger, symbol)
        for symbol in published_market_symbols(ledger)
    )


@dataclass(frozen=True)
class BandIdentityRow:
    symbol: str
    max_leverage: float
    band_rate: float
    inverse_max_leverage: float
    identity_error: float
    identity_holds: bool


def band_identity_report(
    ledger: VerifiedInputLedger, *, tolerance: float = 1e-9
) -> tuple[BandIdentityRow, ...]:
    """Check ``band_rate == 1 / max_leverage`` on every published market."""

    rows: list[BandIdentityRow] = []
    for spec in market_specs(ledger):
        error = spec.band_identity_error
        rows.append(
            BandIdentityRow(
                symbol=spec.symbol,
                max_leverage=spec.max_leverage,
                band_rate=spec.band_rate,
                inverse_max_leverage=1.0 / spec.max_leverage,
                identity_error=error,
                identity_holds=abs(error) <= tolerance,
            )
        )
    return tuple(rows)


@dataclass(frozen=True)
class LeverageZone:
    """Whether the discovery bound protects a position at a chosen leverage."""

    symbol: str
    chosen_leverage: float
    maintenance_margin_rate: float
    liquidation_adverse_move: float
    static_band_rate: float
    reanchored_hard_cap_rate: float
    liquidates_inside_static_band: bool
    liquidates_inside_reanchored_cap: bool
    margin_tiers_modelled: bool = False


def leverage_zone(
    ledger: VerifiedInputLedger, symbol: str, chosen_leverage: float
) -> LeverageZone:
    spec = MarketSpec.from_ledger(ledger, symbol)
    fraction = float(ledger.value("mechanics.maintenance_margin_fraction"))
    adverse = liquidation_adverse_move(
        chosen_leverage=chosen_leverage,
        max_leverage=spec.max_leverage,
        maintenance_margin_fraction=fraction,
    )
    return LeverageZone(
        symbol=symbol,
        chosen_leverage=chosen_leverage,
        maintenance_margin_rate=maintenance_margin_rate(spec.max_leverage, fraction),
        liquidation_adverse_move=adverse,
        static_band_rate=spec.band_rate,
        reanchored_hard_cap_rate=spec.upward_hard_cap_rate,
        liquidates_inside_static_band=adverse <= spec.band_rate,
        liquidates_inside_reanchored_cap=adverse <= spec.upward_hard_cap_rate,
    )


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
    """Path-dependent discovery bound with independent directional budgets.

    The final mark cannot be recovered from the last oracle price alone: a path
    that touches the downward trigger spends part of its budget and ends lower
    than a monotone path with the same terminal price.
    """

    def __init__(
        self,
        *,
        reference_price: float,
        band_rate: float,
        reset_limit: int,
        trigger_fraction: float = 0.90,
    ) -> None:
        if finite(reference_price, "reference_price") <= 0.0:
            raise ValueError("reference_price must be positive")
        if not 0.0 < rate(band_rate, "band_rate") < 1.0:
            raise ValueError("band_rate must be in (0, 1)")
        if reset_limit < 0:
            raise ValueError("reset_limit must be non-negative")
        if not 0.0 < rate(trigger_fraction, "trigger_fraction") <= 1.0:
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
        if finite(raw_price, "raw_price") <= 0.0:
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
        if effective >= upward_trigger and self.upward_resets_used < self.reset_limit:
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

        if finite(live_external_price, "live_external_price") <= 0.0:
            raise ValueError("live_external_price must be positive")
        self.initial_reference_price = live_external_price
        self.reference_price = live_external_price
        self.last_mark_price = live_external_price
        self.upward_resets_used = 0
        self.downward_resets_used = 0

    def theoretical_hard_cap(self, direction: Literal["up", "down"]) -> float:
        if direction not in {"up", "down"}:
            raise ValueError("direction must be 'up' or 'down'")
        multiplier = 1.0 + self.band_rate if direction == "up" else 1.0 - self.band_rate
        return self.initial_reference_price * multiplier ** (self.reset_limit + 1)


def machine_for_market(
    ledger: VerifiedInputLedger,
    symbol: str,
    *,
    reference_price: float,
    reset_limit: int | None = None,
) -> DiscoveryBoundMachine:
    """Build the state machine from published parameters.

    ``reset_limit=0`` reproduces the static band that was actually live before
    the reanchor mechanism shipped; the published budget is a counterfactual for
    events that predate it.
    """

    spec = MarketSpec.from_ledger(ledger, symbol)
    return DiscoveryBoundMachine(
        reference_price=reference_price,
        band_rate=spec.band_rate,
        reset_limit=spec.reset_limit if reset_limit is None else reset_limit,
        trigger_fraction=float(ledger.value("mechanics.reanchor_trigger_fraction")),
    )
