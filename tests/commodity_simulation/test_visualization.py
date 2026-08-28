"""Checks that chart data stays tied to the reviewed commodity models."""

from __future__ import annotations

import unittest

from rwa_market_gap.commodity_simulation import CommoditySimulationEngine
from rwa_market_gap.commodity_simulation.gold import GoldFalsificationResult
from rwa_market_gap.commodity_simulation.visualization import (
    build_gold_discount_chart_data,
    build_gold_ltv_sensitivity_chart_data,
    build_leverage_band_chart_data,
    build_wti_funding_chart_data,
)


def _point_at(series, x: float):
    return next(point for point in series.points if point.x == x)


class WTIFundingChartTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = CommoditySimulationEngine()
        self.chart = build_wti_funding_chart_data(self.engine)

    def test_each_curve_is_zero_at_its_model_break_even(self) -> None:
        for series, break_even in zip(
            self.chart.series, self.chart.break_even_rates
        ):
            with self.subTest(series=series.label):
                self.assertAlmostEqual(_point_at(series, break_even).y, 0.0)

    def test_assumed_funding_points_match_model_net_profit(self) -> None:
        results = self.engine.build().wti.analyze_all()
        for series, result in zip(self.chart.series, results):
            with self.subTest(series=series.label):
                self.assertAlmostEqual(
                    _point_at(series, self.chart.assumed_funding_rate).y,
                    result.ledger.net_profit_usd,
                    places=6,
                )


class GoldDiscountChartTests(unittest.TestCase):
    def setUp(self) -> None:
        self.chart = build_gold_discount_chart_data()

    def test_each_curve_is_zero_at_its_model_break_even(self) -> None:
        for series, break_even in zip(
            self.chart.series, self.chart.break_even_discounts
        ):
            with self.subTest(series=series.label):
                self.assertAlmostEqual(
                    _point_at(series, break_even).y,
                    0.0,
                    places=6,
                )

    def test_observed_divergence_assumption_is_loss_making(self) -> None:
        for series in self.chart.series:
            with self.subTest(series=series.label):
                self.assertLess(
                    _point_at(
                        series, self.chart.tested_divergence_as_discount
                    ).y,
                    0.0,
                )
        self.assertIn("discount assumption", self.chart.assumption_note)


class GoldLTVSensitivityChartTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = CommoditySimulationEngine()
        self.chart = build_gold_ltv_sensitivity_chart_data(self.engine)

    def test_baseline_and_external_proposal_are_separate_landmarks(self) -> None:
        self.assertAlmostEqual(self.chart.official_xaut_max_ltv, 0.70)
        self.assertAlmostEqual(
            self.chart.proposed_paxg_collateral_factor,
            0.75,
        )
        self.assertIn("different token", self.chart.comparison_note)
        counterfactual = self.engine.evidence.record(
            "analysis.gold_counterfactual_max_ltv"
        )
        self.assertEqual(counterfactual.grade, "C")
        self.assertEqual(counterfactual.label, "assumption")
        self.assertEqual(counterfactual.sensitivity, (0.8, 0.9))
        self.assertAlmostEqual(
            self.chart.counterfactual_comparison_ltv,
            float(counterfactual.value),
        )

    def test_higher_ltv_reduces_the_required_discount(self) -> None:
        at_70 = _point_at(
            self.chart.break_even_series,
            self.chart.official_xaut_max_ltv,
        )
        at_86 = _point_at(
            self.chart.break_even_series,
            self.chart.counterfactual_comparison_ltv,
        )
        self.assertGreater(at_70.y, at_86.y)
        self.assertGreater(at_86.y, self.chart.tested_divergence_as_discount)

    def test_reported_minimum_ltv_really_zeroes_net_profit(self) -> None:
        minimum = self.chart.minimum_ltv_at_tested_divergence
        self.assertIsNotNone(minimum)
        assert minimum is not None
        result = self.engine.build().gold.analyze(
            token_discount=self.chart.tested_divergence_as_discount,
            max_ltv=minimum,
        )
        assert isinstance(result, GoldFalsificationResult)
        self.assertAlmostEqual(result.ledger.net_profit_usd, 0.0, delta=0.01)


class LeverageBandChartTests(unittest.TestCase):
    def setUp(self) -> None:
        self.chart = build_leverage_band_chart_data()

    def test_bars_match_reviewed_base_tier_liquidation_moves(self) -> None:
        actual = {
            bar.leverage: bar.liquidation_adverse_move
            for bar in self.chart.bars
        }
        self.assertEqual(set(actual), {5.0, 10.0, 20.0})
        self.assertAlmostEqual(actual[20.0], 0.025)
        self.assertAlmostEqual(actual[10.0], 0.075)
        self.assertAlmostEqual(actual[5.0], 0.175)

    def test_reference_lines_are_static_and_counterfactual_bounds(self) -> None:
        self.assertAlmostEqual(self.chart.static_band_rate, 0.05)
        self.assertAlmostEqual(
            self.chart.counterfactual_reanchor_cap_rate,
            0.157625,
        )
        self.assertFalse(self.chart.margin_tiers_modelled)


if __name__ == "__main__":
    unittest.main()
