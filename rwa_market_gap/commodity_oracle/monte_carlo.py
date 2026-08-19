"""Small, dependency-free Monte Carlo primitives for economic simulations."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from random import Random
from statistics import fmean
from typing import Callable, Sequence

from .evidence import EvidenceRecord


@dataclass(frozen=True)
class EconomicTrial:
    """One simulated attempt with an explicit accounting identity."""

    gross_pfc_usd: float
    coc_usd: float
    capital_at_risk_usd: float
    executed: bool = True

    def __post_init__(self) -> None:
        for name in ("gross_pfc_usd", "coc_usd", "capital_at_risk_usd"):
            if getattr(self, name) < 0.0:
                raise ValueError(f"{name} must be non-negative")

    @property
    def net_profit_usd(self) -> float:
        return self.gross_pfc_usd - self.coc_usd

    @property
    def successful(self) -> bool:
        return self.executed and self.net_profit_usd > 0.0


@dataclass(frozen=True)
class MonteCarloSummary:
    """Aggregate attack economics without hiding unsuccessful attempts."""

    trials: int
    seed: int
    probability_scope: str
    expected_pfc_usd: float
    expected_coc_usd: float
    expected_net_profit_usd: float
    expected_capital_at_risk_usd: float
    execution_probability: float
    success_probability: float
    conditional_success_probability: float
    loss_probability: float
    net_profit_p05_usd: float
    net_profit_median_usd: float
    net_profit_p95_usd: float
    value_at_risk_95_usd: float
    conditional_value_at_risk_95_usd: float


def triangular_from_record(record: EvidenceRecord, rng: Random) -> float:
    """Sample a grade-C assumption from its declared sensitivity interval."""

    if record.grade != "C" or record.label != "assumption":
        raise ValueError(f"{record.path} is not a grade-C assumption")
    if record.sensitivity is None:
        raise ValueError(f"{record.path} has no sensitivity interval")
    low, high = record.sensitivity
    mode = float(record.value)
    if not low <= mode <= high:
        raise ValueError(f"{record.path} mode is outside its sensitivity interval")
    if low == high:
        return low
    return rng.triangular(low, high, mode)


def percentile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ValueError("values must not be empty")
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be in [0, 1]")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def summarize_trials(
    outcomes: Sequence[EconomicTrial],
    *,
    seed: int,
    probability_scope: str,
) -> MonteCarloSummary:
    if not outcomes:
        raise ValueError("outcomes must not be empty")
    nets = [outcome.net_profit_usd for outcome in outcomes]
    executed = [outcome for outcome in outcomes if outcome.executed]
    successes = sum(outcome.successful for outcome in outcomes)
    losses = sum(outcome.net_profit_usd < 0.0 for outcome in outcomes)
    tail_count = max(1, ceil(len(nets) * 0.05))
    lower_tail = sorted(nets)[:tail_count]
    p05 = percentile(nets, 0.05)
    return MonteCarloSummary(
        trials=len(outcomes),
        seed=seed,
        probability_scope=probability_scope,
        expected_pfc_usd=fmean(outcome.gross_pfc_usd for outcome in outcomes),
        expected_coc_usd=fmean(outcome.coc_usd for outcome in outcomes),
        expected_net_profit_usd=fmean(nets),
        expected_capital_at_risk_usd=fmean(
            outcome.capital_at_risk_usd for outcome in outcomes
        ),
        execution_probability=len(executed) / len(outcomes),
        success_probability=successes / len(outcomes),
        conditional_success_probability=(
            sum(outcome.successful for outcome in executed) / len(executed)
            if executed
            else 0.0
        ),
        loss_probability=losses / len(outcomes),
        net_profit_p05_usd=p05,
        net_profit_median_usd=percentile(nets, 0.50),
        net_profit_p95_usd=percentile(nets, 0.95),
        value_at_risk_95_usd=max(0.0, -p05),
        conditional_value_at_risk_95_usd=max(0.0, -fmean(lower_tail)),
    )


def run_trials(
    trial_factory: Callable[[Random], EconomicTrial],
    *,
    trials: int,
    seed: int,
    probability_scope: str,
) -> tuple[MonteCarloSummary, tuple[EconomicTrial, ...]]:
    if trials <= 0:
        raise ValueError("trials must be positive")
    rng = Random(seed)
    outcomes = tuple(trial_factory(rng) for _ in range(trials))
    return (
        summarize_trials(outcomes, seed=seed, probability_scope=probability_scope),
        outcomes,
    )
