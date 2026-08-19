from __future__ import annotations

import unittest

from rwa_market_gap.commodity_oracle.scenarios import CommodityOracleScenarioEngine


class WTITimeGapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = CommodityOracleScenarioEngine()

    def test_hormuz_golden_case(self) -> None:
        result = self.engine.wti_time_gap()
        self.assertAlmostEqual(result.theoretical_v1_cap_usd, 95.9175)
        self.assertAlmostEqual(result.onchain_recognized_move, 0.049075, places=5)
        self.assertAlmostEqual(result.actual_reopen_move, 0.170115, places=5)
        self.assertAlmostEqual(
            result.unrecognized_gap_percentage_points, 0.12104, places=5
        )
        self.assertAlmostEqual(result.counterfactual_v2_cap_rate, 0.157625)
        self.assertAlmostEqual(result.counterfactual_v2_cap_usd, 105.7490, places=3)
        self.assertAlmostEqual(
            result.reopen_move_beyond_v2_cap_percentage_points,
            0.01249,
            places=4,
        )
        self.assertEqual(result.minimum_clamped_updates, 25)

    def test_observed_liquidation_does_not_become_unverified_adl_claim(self) -> None:
        result = self.engine.wti_time_gap()
        self.assertAlmostEqual(result.short_to_long_liquidation_ratio, 17.5714286)
        self.assertFalse(result.reanchor_was_active_during_event)
        self.assertFalse(result.adl_was_confirmed)

    def test_leverage_zones_match_documented_selective_protection(self) -> None:
        lev20 = self.engine.leverage_zone("WTIOIL", 20.0)
        lev10 = self.engine.leverage_zone("WTIOIL", 10.0)
        lev5 = self.engine.leverage_zone("WTIOIL", 5.0)
        self.assertTrue(lev20.liquidates_during_v1_gap)
        self.assertFalse(lev10.liquidates_during_v1_gap)
        self.assertTrue(lev10.liquidates_during_v2_gap)
        self.assertFalse(lev5.liquidates_during_v2_gap)
        self.assertFalse(lev20.margin_tiers_modelled)

    def test_wti_loss_transfer_example_is_labelled_assumption_input(self) -> None:
        result = self.engine.wti_limited_liability_example()
        self.assertAlmostEqual(result.initial_margin_usd, 1_000_000.0)
        self.assertAlmostEqual(result.deficit_usd, 2_402_298.8506, places=2)


class NaturalGasBenchmarkTests(unittest.TestCase):
    def test_asian_risk_and_onchain_proxy_move_in_opposite_directions(self) -> None:
        result = CommodityOracleScenarioEngine().natural_gas_benchmark_gap()
        self.assertAlmostEqual(result.target_change, 0.828)
        self.assertAlmostEqual(result.proxy_change, -0.091)
        self.assertAlmostEqual(result.benchmark_gap_percentage_points, 0.919)
        self.assertAlmostEqual(result.proxy_hedge_shortfall_usd, 919_000.0)
        self.assertTrue(result.moves_in_opposite_directions)
        self.assertEqual(result.loss_path, ("market_liquidation", "adl"))


class GoldHierarchyGapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = CommodityOracleScenarioEngine()

    def test_protocol_and_user_buffers_are_distinct(self) -> None:
        result = self.engine.gold_hierarchy_gap()
        self.assertAlmostEqual(result.liquidation_start_gap, 1.0 - 0.70 / 0.75)
        self.assertAlmostEqual(result.protocol_insolvency_buffer, 0.205)

    def test_observed_discount_leaves_only_one_point_five_percent(self) -> None:
        result = self.engine.gold_hierarchy_gap()
        self.assertAlmostEqual(result.liquidator_residual_margin, 0.015)
        self.assertTrue(result.liquidator_economically_incentivized)
        self.assertFalse(result.secondary_holder_can_redeem)

    def test_liquidator_opts_out_when_discount_consumes_full_bonus(self) -> None:
        result = self.engine.gold_hierarchy_gap(token_discount=0.06)
        self.assertAlmostEqual(result.liquidator_residual_margin, 0.0)
        self.assertFalse(result.liquidator_economically_incentivized)

    def test_debt_cap_fits_but_supply_cap_exceeds_measured_capacity(self) -> None:
        result = self.engine.gold_hierarchy_gap()
        self.assertAlmostEqual(result.debt_cap_to_capacity, 3_000_000 / 9_440_000)
        self.assertAlmostEqual(
            result.supply_cap_usd_at_liquidity_snapshot,
            9_440_000 * 5_000 / 2_800,
        )
        self.assertAlmostEqual(result.current_marked_supply_cap_usd, 21_770_000.0)
        self.assertAlmostEqual(result.supply_cap_to_capacity, 5_000 / 2_800)
        self.assertGreater(result.supply_above_capacity_usd, 0.0)
        self.assertFalse(result.borrowing_token_itself_enabled)


if __name__ == "__main__":
    unittest.main()
