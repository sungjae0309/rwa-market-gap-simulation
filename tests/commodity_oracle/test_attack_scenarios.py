from __future__ import annotations

import unittest

from rwa_market_gap.commodity_oracle.attack_scenarios import (
    CommodityAttackEconomicsEngine,
)


class WTIAttackEconomicsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = CommodityAttackEconomicsEngine()

    def test_residual_samples_are_derived_from_two_observed_stress_events(self) -> None:
        result = self.engine.wti_gap_attack(trials=100, seed=11)
        expected_first = (75.0 - 70.64) / 70.64
        expected_second = (106.89 - 95.833) / 95.833
        self.assertEqual(result.empirical_sample_count, 2)
        self.assertAlmostEqual(result.residual_gap_samples[0], expected_first)
        self.assertAlmostEqual(result.residual_gap_samples[1], expected_second)

    def test_default_seed_is_reproducible(self) -> None:
        first = self.engine.wti_gap_attack(trials=2_000, seed=29)
        second = self.engine.wti_gap_attack(trials=2_000, seed=29)
        self.assertEqual(first.summary, second.summary)

    def test_probability_is_explicitly_stress_conditional(self) -> None:
        result = self.engine.wti_gap_attack(trials=500, seed=5)
        self.assertIn("conditional", result.summary.probability_scope)
        self.assertIn("not an unconditional", result.summary.probability_scope)

    def test_deployer_bond_increases_coc_capital_and_tail_loss(self) -> None:
        trader = self.engine.wti_gap_attack(
            actor="strategic_trader", trials=10_000, seed=17
        )
        deployer = self.engine.wti_gap_attack(
            actor="market_deployer", trials=10_000, seed=17
        )
        self.assertGreater(
            deployer.summary.expected_coc_usd, trader.summary.expected_coc_usd
        )
        self.assertGreater(
            deployer.summary.expected_capital_at_risk_usd,
            trader.summary.expected_capital_at_risk_usd,
        )
        self.assertGreater(
            deployer.summary.conditional_value_at_risk_95_usd,
            trader.summary.conditional_value_at_risk_95_usd,
        )
        self.assertGreater(
            deployer.break_even_residual_gap_rate,
            trader.break_even_residual_gap_rate,
        )

    def test_trader_success_rate_is_close_to_observed_direction_match_rate(self) -> None:
        result = self.engine.wti_gap_attack(trials=20_000, seed=31)
        self.assertAlmostEqual(
            result.summary.success_probability,
            result.direction_accuracy,
            delta=0.015,
        )


class GoldAttackEconomicsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = CommodityAttackEconomicsEngine()

    def test_observed_discount_does_not_cover_collateral_purchase(self) -> None:
        result = self.engine.gold_stale_collateral_attack(trials=500, seed=1)
        self.assertFalse(result.profitable_within_observed_envelope)
        self.assertGreater(result.break_even_discount, result.observed_max_discount)
        self.assertLess(self.engine.gold_profit_at_discount(0.045), 0.0)

    def test_attack_can_succeed_only_beyond_the_break_even_discount(self) -> None:
        result = self.engine.gold_stale_collateral_attack(trials=100, seed=2)
        below = self.engine.gold_profit_at_discount(
            result.break_even_discount - 0.001
        )
        above = self.engine.gold_profit_at_discount(
            result.break_even_discount + 0.001
        )
        self.assertLess(below, 0.0)
        self.assertGreater(above, 0.0)

    def test_observed_discount_envelope_has_zero_success_probability(self) -> None:
        result = self.engine.gold_stale_collateral_attack(
            trials=10_000, seed=41
        )
        self.assertEqual(result.summary.success_probability, 0.0)
        self.assertLess(result.summary.expected_net_profit_usd, 0.0)


class NaturalGasClassificationTests(unittest.TestCase):
    def test_benchmark_failure_is_not_relabelled_as_attack(self) -> None:
        result = CommodityAttackEconomicsEngine().natural_gas_attack_assessment()
        self.assertFalse(result.classified_as_attack)
        self.assertIsNone(result.attack_success_probability)
        self.assertAlmostEqual(result.observed_benchmark_gap_percentage_points, 0.919)


if __name__ == "__main__":
    unittest.main()
