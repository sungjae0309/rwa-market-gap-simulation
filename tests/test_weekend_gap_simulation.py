from __future__ import annotations

import unittest
from dataclasses import replace

from weekend_gap_config import WeekendGapConfig
from weekend_gap_simulation import WeekendGapEngine


class WeekendGapThresholdTests(unittest.TestCase):
    def test_document_thresholds_for_ltv_70_bonus_5(self) -> None:
        engine = WeekendGapEngine()

        self.assertAlmostEqual(engine.attack_profit_threshold, 0.30)
        self.assertAlmostEqual(
            engine.liquidation_incentive_shortfall_threshold, 0.265
        )

    def test_lower_ltv_raises_attack_threshold(self) -> None:
        low_ltv = WeekendGapEngine(WeekendGapConfig(ltv=0.60))
        high_ltv = WeekendGapEngine(WeekendGapConfig(ltv=0.80))

        self.assertGreater(
            low_ltv.attack_profit_threshold,
            high_ltv.attack_profit_threshold,
        )

    def test_ltv_cannot_exceed_liquidation_threshold(self) -> None:
        with self.assertRaises(ValueError):
            WeekendGapConfig(ltv=0.81, liquidation_threshold=0.80)


class WeekendGapPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = WeekendGapEngine()

    def test_document_gap_path_at_10_20_30_35_percent(self) -> None:
        g10, g20, g30, g35 = self.engine.sweep_gaps((0.10, 0.20, 0.30, 0.35))

        self.assertFalse(g10.liquidatable)
        self.assertAlmostEqual(g10.attacker_terminal_wealth_usd, 900_000.0)
        self.assertAlmostEqual(g10.gross_incremental_profit_usd, 0.0)

        self.assertTrue(g20.liquidatable)
        self.assertAlmostEqual(g20.attacker_terminal_wealth_usd, 765_000.0)
        self.assertAlmostEqual(g20.gross_incremental_profit_usd, -35_000.0)

        self.assertAlmostEqual(g30.attacker_terminal_wealth_usd, 700_000.0)
        self.assertAlmostEqual(g30.gross_incremental_profit_usd, 0.0)

        self.assertTrue(g35.strategically_defaults)
        self.assertAlmostEqual(g35.attacker_terminal_wealth_usd, 700_000.0)
        self.assertAlmostEqual(g35.gross_incremental_profit_usd, 50_000.0)
        self.assertAlmostEqual(g35.principal_bad_debt_usd, 50_000.0)

    def test_document_interest_and_transaction_costs(self) -> None:
        outcome = self.engine.realized(0.35)

        self.assertAlmostEqual(outcome.interest_cost_usd, 230.1369863)
        self.assertEqual(outcome.transaction_cost_usd, 200.0)
        self.assertAlmostEqual(outcome.net_incremental_profit_usd, 49_569.8630137)

    def test_borrow_vs_sell_matches_cpmm_crossing(self) -> None:
        default = self.engine.realized(0.35)
        larger_position = WeekendGapEngine(
            replace(self.engine.config, collateral_value_usd=2_000_000.0)
        ).realized(0.35)

        self.assertAlmostEqual(
            default.minimum_collateral_for_borrow_advantage_usd,
            3_000_000.0 * 0.30 / 0.70,
        )
        self.assertFalse(default.prefers_borrow_to_amm_sale)
        self.assertTrue(larger_position.prefers_borrow_to_amm_sale)

    def test_disabling_new_borrowing_disables_active_attack(self) -> None:
        engine = WeekendGapEngine(
            replace(self.engine.config, new_borrowing_enabled=False)
        )
        outcome = engine.realized(0.50)
        expected = engine.expected(
            success_probability=1.0,
            expected_success_gap=0.50,
        )

        self.assertFalse(outcome.borrowing_enabled)
        self.assertEqual(outcome.borrowed_usd, 0.0)
        self.assertEqual(outcome.net_incremental_profit_usd, 0.0)
        self.assertEqual(expected.expected_net_profit_usd, 0.0)


class WeekendGapExpectationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = WeekendGapEngine()

    def test_document_probability_threshold_and_fixed_cost_adjustment(self) -> None:
        outcome = self.engine.expected(
            success_probability=0.26,
            expected_success_gap=0.40,
        )

        self.assertAlmostEqual(outcome.conditional_success_profit_usd, 100_000.0)
        self.assertAlmostEqual(outcome.failure_liquidation_penalty_usd, 35_000.0)
        self.assertAlmostEqual(
            outcome.simplified_break_even_probability,
            35_000.0 / 135_000.0,
        )
        self.assertGreater(
            outcome.exact_break_even_probability,
            outcome.simplified_break_even_probability,
        )
        self.assertLess(outcome.expected_net_profit_usd, 0.0)

    def test_liquidator_participates_only_when_bonus_covers_gap_risk(self) -> None:
        calm = self.engine.liquidator_participation(gap_quantile=0.0213)
        stressed = self.engine.liquidator_participation(gap_quantile=0.0523)

        self.assertTrue(calm.participates)
        self.assertFalse(stressed.participates)
        self.assertAlmostEqual(calm.funding_cost_rate, 0.0003287671)


if __name__ == "__main__":
    unittest.main()
