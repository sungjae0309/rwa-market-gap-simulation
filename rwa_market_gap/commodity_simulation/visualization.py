"""Chart-ready data derived only from the existing commodity models."""

from __future__ import annotations

from dataclasses import dataclass

from .gold import GoldFalsificationResult
from .suite import CommoditySimulationEngine


@dataclass(frozen=True)
class ChartPoint:
    x: float
    y: float


@dataclass(frozen=True)
class LineSeries:
    label: str
    points: tuple[ChartPoint, ...]


@dataclass(frozen=True)
class WTIFundingChartData:
    series: tuple[LineSeries, ...]
    break_even_rates: tuple[float, ...]
    assumed_funding_rate: float
    declared_sensitivity_low: float
    declared_sensitivity_high: float
    x_min: float
    x_max: float


@dataclass(frozen=True)
class GoldDiscountChartData:
    series: tuple[LineSeries, ...]
    break_even_discounts: tuple[float, ...]
    tested_divergence_as_discount: float
    x_min: float
    x_max: float
    assumption_note: str


@dataclass(frozen=True)
class LeverageBar:
    leverage: float
    liquidation_adverse_move: float


@dataclass(frozen=True)
class LeverageBandChartData:
    bars: tuple[LeverageBar, ...]
    static_band_rate: float
    counterfactual_reanchor_cap_rate: float
    margin_tiers_modelled: bool


def _linspace(start: float, stop: float, count: int) -> tuple[float, ...]:
    if count < 2:
        raise ValueError("count must be at least two")
    step = (stop - start) / (count - 1)
    return tuple(start + step * index for index in range(count))


def _with_landmarks(
    values: tuple[float, ...], landmarks: tuple[float, ...]
) -> tuple[float, ...]:
    return tuple(sorted(set(values + landmarks)))


def build_wti_funding_chart_data(
    engine: CommoditySimulationEngine | None = None,
    *,
    samples: int = 121,
) -> WTIFundingChartData:
    """Net profit against 49-hour funding using the model's closed form.

    The domain extends to ten percent beyond the larger break-even rate only so
    both zero crossings are visible. It is a diagnostic display range, not a
    claim about observed funding.
    """

    resolved_engine = engine or CommoditySimulationEngine()
    results = resolved_engine.build().wti.analyze_all()
    break_evens = tuple(
        result.break_even_funding_rate_over_horizon for result in results
    )
    x_min = min(result.funding_sensitivity_low for result in results)
    x_max = max(break_evens) * 1.10
    assumed = results[0].assumed_funding_rate_over_horizon
    x_values = _with_landmarks(
        _linspace(x_min, x_max, samples),
        break_evens + (assumed,),
    )
    labels = ("Stress weekend 1", "Stress weekend 2")
    series: list[LineSeries] = []
    for label, result in zip(labels, results):
        notional = result.capacity.executable_notional_usd
        points = tuple(
            ChartPoint(
                x=funding_rate,
                y=notional
                * (
                    result.break_even_funding_rate_over_horizon
                    - funding_rate
                ),
            )
            for funding_rate in x_values
        )
        series.append(LineSeries(label=label, points=points))
    return WTIFundingChartData(
        series=tuple(series),
        break_even_rates=break_evens,
        assumed_funding_rate=assumed,
        declared_sensitivity_low=min(
            result.funding_sensitivity_low for result in results
        ),
        declared_sensitivity_high=max(
            result.funding_sensitivity_high for result in results
        ),
        x_min=x_min,
        x_max=x_max,
    )


def build_gold_discount_chart_data(
    engine: CommoditySimulationEngine | None = None,
    *,
    samples: int = 121,
) -> GoldDiscountChartData:
    """Net profit across assumed acquisition discounts for three impact curves."""

    resolved_engine = engine or CommoditySimulationEngine()
    gold = resolved_engine.build().gold
    exponents = (0.5, 1.0, 2.0)
    baseline_results: list[GoldFalsificationResult] = []
    for exponent in exponents:
        result = gold.with_impact_exponent(exponent).analyze()
        if not isinstance(result, GoldFalsificationResult):
            raise AssertionError("the supplied stale state should be executable")
        baseline_results.append(result)
    break_evens = tuple(
        result.modelled_break_even_discount for result in baseline_results
    )
    tested_divergence = baseline_results[0].tested_discount_assumption
    x_min = 0.0
    x_max = max(break_evens) * 1.20
    x_values = _with_landmarks(
        _linspace(x_min, x_max, samples),
        break_evens + (tested_divergence,),
    )
    series: list[LineSeries] = []
    for exponent in exponents:
        model = gold.with_impact_exponent(exponent)
        points: list[ChartPoint] = []
        for discount in x_values:
            result = model.analyze(token_discount=discount)
            if not isinstance(result, GoldFalsificationResult):
                raise AssertionError("the supplied stale state should be executable")
            points.append(
                ChartPoint(x=discount, y=result.ledger.net_profit_usd)
            )
        series.append(
            LineSeries(label=f"Impact exponent {exponent:.1f}", points=tuple(points))
        )
    return GoldDiscountChartData(
        series=tuple(series),
        break_even_discounts=break_evens,
        tested_divergence_as_discount=tested_divergence,
        x_min=x_min,
        x_max=x_max,
        assumption_note=baseline_results[0].tested_discount_source,
    )


def build_leverage_band_chart_data(
    engine: CommoditySimulationEngine | None = None,
) -> LeverageBandChartData:
    """Base-tier WTI liquidation moves against the two published bounds."""

    resolved_engine = engine or CommoditySimulationEngine()
    zones = tuple(
        resolved_engine.leverage_zone("WTIOIL", leverage)
        for leverage in (5.0, 10.0, 20.0)
    )
    return LeverageBandChartData(
        bars=tuple(
            LeverageBar(
                leverage=zone.chosen_leverage,
                liquidation_adverse_move=zone.liquidation_adverse_move,
            )
            for zone in zones
        ),
        static_band_rate=zones[0].static_band_rate,
        counterfactual_reanchor_cap_rate=zones[0].reanchored_hard_cap_rate,
        margin_tiers_modelled=any(zone.margin_tiers_modelled for zone in zones),
    )
