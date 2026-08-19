"""Margin, limited-liability, and simplified contract-space ADL logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal


MarginMode = Literal["cross", "isolated"]


def maintenance_margin_rate(
    max_leverage: float, maintenance_margin_fraction: float
) -> float:
    """Maintenance margin fixed from the market's maximum leverage."""

    if max_leverage <= 0.0:
        raise ValueError("max_leverage must be positive")
    if not 0.0 < maintenance_margin_fraction <= 1.0:
        raise ValueError("maintenance_margin_fraction must be in (0, 1]")
    return maintenance_margin_fraction / max_leverage


def liquidation_adverse_move(
    *,
    chosen_leverage: float,
    max_leverage: float,
    maintenance_margin_fraction: float,
) -> float:
    """Adverse move that starts liquidation under the simplified base tier."""

    if chosen_leverage <= 0.0 or chosen_leverage > max_leverage:
        raise ValueError("chosen_leverage must be in (0, max_leverage]")
    return 1.0 / chosen_leverage - maintenance_margin_rate(
        max_leverage, maintenance_margin_fraction
    )


def loss_path(margin_mode: MarginMode) -> tuple[str, ...]:
    if margin_mode == "cross":
        return ("market_liquidation", "backstop_liquidator", "adl")
    if margin_mode == "isolated":
        return ("market_liquidation", "adl")
    raise ValueError(f"unsupported margin mode: {margin_mode}")


@dataclass(frozen=True)
class LimitedLiabilityResult:
    notional_usd: float
    chosen_leverage: float
    adverse_move: float
    initial_margin_usd: float
    true_loss_usd: float
    trader_borne_loss_usd: float
    deficit_usd: float


def limited_liability_loss(
    *, notional_usd: float, chosen_leverage: float, adverse_move: float
) -> LimitedLiabilityResult:
    if notional_usd < 0.0:
        raise ValueError("notional_usd must be non-negative")
    if chosen_leverage <= 0.0:
        raise ValueError("chosen_leverage must be positive")
    if adverse_move < 0.0:
        raise ValueError("adverse_move must be non-negative")
    margin = notional_usd / chosen_leverage
    true_loss = notional_usd * adverse_move
    borne = min(true_loss, margin)
    return LimitedLiabilityResult(
        notional_usd=notional_usd,
        chosen_leverage=chosen_leverage,
        adverse_move=adverse_move,
        initial_margin_usd=margin,
        true_loss_usd=true_loss,
        trader_borne_loss_usd=borne,
        deficit_usd=max(0.0, true_loss - borne),
    )


@dataclass(frozen=True)
class ADLCandidate:
    account_id: str
    contracts: float
    entry_price: float
    mark_price: float
    account_value_usd: float
    fair_price: float

    def __post_init__(self) -> None:
        if not self.account_id.strip():
            raise ValueError("account_id must not be blank")
        for name in (
            "contracts",
            "entry_price",
            "mark_price",
            "account_value_usd",
            "fair_price",
        ):
            if getattr(self, name) <= 0.0:
                raise ValueError(f"{name} must be positive")
        if self.fair_price < self.mark_price:
            raise ValueError("long-side ADL candidate must have fair_price >= mark_price")

    @property
    def notional_usd(self) -> float:
        return self.contracts * self.mark_price

    @property
    def rank(self) -> float:
        return (self.mark_price / self.entry_price) * (
            self.notional_usd / self.account_value_usd
        )

    @property
    def opportunity_profit_per_contract_usd(self) -> float:
        return self.fair_price - self.mark_price


@dataclass(frozen=True)
class ADLAction:
    account_id: str
    rank: float
    contracts_closed: float
    foregone_profit_usd: float


@dataclass(frozen=True)
class ADLAllocation:
    requested_deficit_usd: float
    allocated_deficit_usd: float
    remaining_deficit_usd: float
    actions: tuple[ADLAction, ...]


def allocate_adl(
    deficit_usd: float, candidates: Iterable[ADLCandidate]
) -> ADLAllocation:
    """Allocate a deficit in contract space using the documented rank formula.

    This is a deliberately bounded research allocator, not an exchange replica.
    It closes contract quantities at the stale mark until their foregone fair-
    value profit covers the requested deficit.
    """

    if deficit_usd < 0.0:
        raise ValueError("deficit_usd must be non-negative")
    remaining = deficit_usd
    actions: list[ADLAction] = []
    for candidate in sorted(candidates, key=lambda item: item.rank, reverse=True):
        if remaining <= 1e-9:
            break
        per_contract = candidate.opportunity_profit_per_contract_usd
        if per_contract <= 0.0:
            continue
        contracts = min(candidate.contracts, remaining / per_contract)
        haircut = contracts * per_contract
        actions.append(
            ADLAction(
                account_id=candidate.account_id,
                rank=candidate.rank,
                contracts_closed=contracts,
                foregone_profit_usd=haircut,
            )
        )
        remaining = max(0.0, remaining - haircut)
    allocated = deficit_usd - remaining
    if abs(allocated + remaining - deficit_usd) > 1e-6:
        raise AssertionError("ADL deficit conservation failed")
    return ADLAllocation(
        requested_deficit_usd=deficit_usd,
        allocated_deficit_usd=allocated,
        remaining_deficit_usd=remaining,
        actions=tuple(actions),
    )


def assert_matched_notional(
    long_notionals: Iterable[float], short_notionals: Iterable[float], *, tolerance: float = 1e-6
) -> None:
    longs = tuple(long_notionals)
    shorts = tuple(short_notionals)
    if any(value < 0.0 for value in (*longs, *shorts)):
        raise ValueError("notionals must be non-negative")
    long_total = sum(longs)
    short_total = sum(shorts)
    if abs(long_total - short_total) > tolerance:
        raise AssertionError(
            f"long/short notional mismatch: {long_total} != {short_total}"
        )
