"""Published-parameter mechanics: the band identity, hard caps, margin zones.

These follow the mandatory checks in the scenario's code-verification guide.
Mechanics expectations come from the venue's published example; event values
come from the supplied evidence ledger rather than this implementation's output.
"""

from __future__ import annotations

import unittest

from rwa_market_gap.commodity_simulation import CommoditySimulationEngine
from rwa_market_gap.commodity_simulation.market_mechanics import (
    DiscoveryBoundMachine,
    MarketSpec,
    band_identity_report,
    leverage_zone,
    liquidation_collateral_scope,
    liquidation_adverse_move,
    machine_for_market,
    maintenance_margin_rate,
    market_specs,
)


class BandIdentityTests(unittest.TestCase):
    """T1: band width equals the inverse of maximum leverage."""

    def setUp(self) -> None:
        self.engine = CommoditySimulationEngine()

    def test_identity_holds_on_every_published_market(self) -> None:
        rows = band_identity_report(self.engine.evidence)
        self.assertGreaterEqual(len(rows), 5)
        for row in rows:
            with self.subTest(market=row.symbol):
                self.assertAlmostEqual(
                    row.band_rate, 1.0 / row.max_leverage, places=12
                )
                self.assertTrue(row.identity_holds)

    def test_published_pairs_match_the_scenario_table(self) -> None:
        expected = {
            "GOLD": (25.0, 0.04),
            "WTIOIL": (20.0, 0.05),
            "NATGAS": (10.0, 0.10),
            "SILVER": (25.0, 0.04),
            "BRENTOIL": (20.0, 0.05),
        }
        actual = {
            spec.symbol: (spec.max_leverage, spec.band_rate)
            for spec in market_specs(self.engine.evidence)
        }
        for symbol, pair in expected.items():
            with self.subTest(market=symbol):
                self.assertAlmostEqual(actual[symbol][0], pair[0])
                self.assertAlmostEqual(actual[symbol][1], pair[1])

    def test_band_ceiling_equals_max_leverage_bankruptcy_move(self) -> None:
        for spec in market_specs(self.engine.evidence):
            with self.subTest(market=spec.symbol):
                self.assertAlmostEqual(
                    spec.band_rate, spec.bankruptcy_move_at_max_leverage, places=12
                )

    def test_a_broken_identity_is_reported_as_broken(self) -> None:
        spec = MarketSpec(
            symbol="TEST",
            feed="Test.FEED",
            max_leverage=20.0,
            band_rate=0.07,
            reset_limit=2,
            margin_mode="cross",
            external_session="Sun 18:00 ET-Fri 17:00 ET",
        )
        self.assertAlmostEqual(spec.band_identity_error, 0.02)


class PublishedHardCapTests(unittest.TestCase):
    """T2: reproduce the venue's published +15.76% / -14.26% example."""

    def _monotone(self, direction: str) -> float:
        machine = DiscoveryBoundMachine(
            reference_price=100.0, band_rate=0.05, reset_limit=2
        )
        feed = 1_000.0 if direction == "up" else 0.001
        return machine.process([feed] * 6)[-1].effective_mark_price

    def test_monotone_up_reaches_the_published_ceiling(self) -> None:
        self.assertAlmostEqual(self._monotone("up"), 115.7625, places=4)

    def test_monotone_down_reaches_the_published_floor(self) -> None:
        self.assertAlmostEqual(self._monotone("down"), 85.7375, places=4)

    def test_closed_form_cap_matches_the_sequential_machine(self) -> None:
        machine = DiscoveryBoundMachine(
            reference_price=100.0, band_rate=0.05, reset_limit=2
        )
        self.assertAlmostEqual(
            machine.theoretical_hard_cap("up"), self._monotone("up"), places=9
        )

    def test_hard_cap_is_not_reachable_without_reanchor(self) -> None:
        machine = DiscoveryBoundMachine(
            reference_price=100.0, band_rate=0.05, reset_limit=0
        )
        self.assertAlmostEqual(
            machine.process([1_000.0] * 6)[-1].effective_mark_price, 105.0, places=9
        )


class PathDependenceTests(unittest.TestCase):
    """The guide's worked example: the same terminal price, two paths."""

    def _run(self, prices: list[float]):
        machine = DiscoveryBoundMachine(
            reference_price=100.0, band_rate=0.05, reset_limit=2
        )
        return machine.process(prices)[-1]

    def test_monotone_path_spends_only_upward_budget(self) -> None:
        step = self._run([102.0, 106.0, 110.0, 112.0])
        self.assertAlmostEqual(step.effective_mark_price, 112.00, places=2)
        self.assertEqual((step.upward_resets_used, step.downward_resets_used), (2, 0))

    def test_sawtooth_path_ends_lower_at_the_same_terminal_price(self) -> None:
        step = self._run([102.0, 94.0, 100.0, 106.0, 110.0, 112.0])
        self.assertAlmostEqual(step.effective_mark_price, 109.97, places=2)
        self.assertEqual((step.upward_resets_used, step.downward_resets_used), (2, 1))

    def test_terminal_price_alone_cannot_determine_the_mark(self) -> None:
        monotone = self._run([102.0, 106.0, 110.0, 112.0])
        sawtooth = self._run([102.0, 94.0, 100.0, 106.0, 110.0, 112.0])
        self.assertGreater(
            monotone.effective_mark_price, sawtooth.effective_mark_price
        )

    def test_directional_budgets_are_independent(self) -> None:
        machine = DiscoveryBoundMachine(
            reference_price=100.0, band_rate=0.05, reset_limit=2
        )
        machine.process([1_000.0, 1_000.0])
        self.assertEqual(machine.upward_resets_used, 2)
        self.assertEqual(machine.downward_resets_used, 0)

    def test_external_session_reopen_clears_both_counters(self) -> None:
        machine = DiscoveryBoundMachine(
            reference_price=100.0, band_rate=0.05, reset_limit=2
        )
        machine.process([1_000.0, 1_000.0])
        machine.reset_for_external_session(120.0)
        self.assertEqual(machine.upward_resets_used, 0)
        self.assertEqual(machine.downward_resets_used, 0)
        self.assertAlmostEqual(machine.reference_price, 120.0)


class MaintenanceMarginTests(unittest.TestCase):
    """The guide's second critical error: maintenance margin is not chosen-leverage."""

    def test_maintenance_margin_is_fixed_by_the_market_maximum(self) -> None:
        fixed = maintenance_margin_rate(20.0, 0.5)
        self.assertAlmostEqual(fixed, 0.025, places=12)
        # The only term that varies with chosen leverage is 1/L, so the
        # liquidation move plus a constant maintenance rate must equal 1/L.
        for chosen in (20.0, 10.0, 5.0, 2.0):
            with self.subTest(chosen=chosen):
                move = liquidation_adverse_move(
                    chosen_leverage=chosen,
                    max_leverage=20.0,
                    maintenance_margin_fraction=0.5,
                )
                self.assertAlmostEqual(move + fixed, 1.0 / chosen, places=12)

    def test_published_liquidation_moves(self) -> None:
        expected = {20.0: 0.025, 10.0: 0.075, 5.0: 0.175}
        for chosen, move in expected.items():
            with self.subTest(chosen=chosen):
                self.assertAlmostEqual(
                    liquidation_adverse_move(
                        chosen_leverage=chosen,
                        max_leverage=20.0,
                        maintenance_margin_fraction=0.5,
                    ),
                    move,
                    places=12,
                )

    def test_chosen_leverage_formula_would_invert_the_conclusion(self) -> None:
        # The wrong model sets maintenance to 1/(2*chosen), which collapses the
        # liquidation move to 1/(2L) at every leverage. The guide's table:
        #   20x -> 2.50% (same)   10x -> 5.00% vs 7.50%   5x -> 10.00% vs 17.50%
        def wrong(chosen: float) -> float:
            return 1.0 / chosen - 1.0 / (2.0 * chosen)

        def right(chosen: float) -> float:
            return liquidation_adverse_move(
                chosen_leverage=chosen,
                max_leverage=20.0,
                maintenance_margin_fraction=0.5,
            )

        for chosen, wrong_move, right_move in (
            (20.0, 0.025, 0.025),
            (10.0, 0.050, 0.075),
            (5.0, 0.100, 0.175),
        ):
            with self.subTest(chosen=chosen):
                self.assertAlmostEqual(wrong(chosen), wrong_move, places=12)
                self.assertAlmostEqual(right(chosen), right_move, places=12)

        static_band = 0.05
        reanchored_cap = (1.0 + static_band) ** 3 - 1.0
        # 10x flips at the static band, 5x flips at the reanchored cap.
        self.assertLessEqual(wrong(10.0), static_band)
        self.assertGreater(right(10.0), static_band)
        self.assertLess(wrong(5.0), reanchored_cap)
        self.assertGreater(right(5.0), reanchored_cap)

    def test_chosen_leverage_above_the_market_maximum_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            liquidation_adverse_move(
                chosen_leverage=21.0,
                max_leverage=20.0,
                maintenance_margin_fraction=0.5,
            )


class LeverageZoneTests(unittest.TestCase):
    """The band protects only the middle of the leverage range."""

    def setUp(self) -> None:
        self.engine = CommoditySimulationEngine()

    def test_max_leverage_liquidates_inside_the_static_band(self) -> None:
        zone = leverage_zone(self.engine.evidence, "WTIOIL", 20.0)
        self.assertAlmostEqual(zone.liquidation_adverse_move, 0.025)
        self.assertTrue(zone.liquidates_inside_static_band)

    def test_mid_leverage_is_protected_by_the_static_band(self) -> None:
        zone = leverage_zone(self.engine.evidence, "WTIOIL", 10.0)
        self.assertAlmostEqual(zone.liquidation_adverse_move, 0.075)
        self.assertFalse(zone.liquidates_inside_static_band)

    def test_low_leverage_survives_even_the_reanchored_cap(self) -> None:
        zone = leverage_zone(self.engine.evidence, "WTIOIL", 5.0)
        self.assertAlmostEqual(zone.liquidation_adverse_move, 0.175)
        self.assertFalse(zone.liquidates_inside_reanchored_cap)

    def test_margin_tiers_are_declared_unmodelled(self) -> None:
        zone = leverage_zone(self.engine.evidence, "WTIOIL", 10.0)
        self.assertFalse(zone.margin_tiers_modelled)


class MarginScopeTests(unittest.TestCase):
    def test_cross_margin_exposes_the_shared_cross_scope(self) -> None:
        self.assertEqual(
            liquidation_collateral_scope("cross"),
            ("cross_positions", "cross_margin_balance"),
        )

    def test_isolated_margin_limits_the_collateral_scope(self) -> None:
        self.assertEqual(
            liquidation_collateral_scope("isolated"),
            ("isolated_position", "isolated_margin_balance"),
        )

    def test_natural_gas_is_the_isolated_market(self) -> None:
        engine = CommoditySimulationEngine()
        specs = {spec.symbol: spec for spec in market_specs(engine.evidence)}
        self.assertEqual(
            specs["NATGAS"].liquidation_collateral_scope,
            ("isolated_position", "isolated_margin_balance"),
        )
        for symbol in ("GOLD", "WTIOIL", "SILVER", "BRENTOIL"):
            with self.subTest(market=symbol):
                self.assertEqual(
                    specs[symbol].liquidation_collateral_scope,
                    ("cross_positions", "cross_margin_balance"),
                )


class HormuzGoldenCaseTests(unittest.TestCase):
    """T3: the second stress weekend against the published ceilings."""

    def setUp(self) -> None:
        self.engine = CommoditySimulationEngine()
        self.cme_close = float(
            self.engine.evidence.value(
                "events.wti_second_weekend.friday_cme_close_usd"
            )
        )
        self.observed_mark = float(
            self.engine.evidence.value(
                "events.wti_second_weekend.observed_onchain_mark_usd"
            )
        )
        self.mark_is_upper_bound = bool(
            self.engine.evidence.value(
                "events.wti_second_weekend."
                "observed_onchain_mark_is_static_upper_bound"
            )
        )
        self.reopen = float(
            self.engine.evidence.value(
                "events.wti_second_weekend.cme_reopen_price_usd"
            )
        )
        self.short_liquidations = float(
            self.engine.evidence.value(
                "events.wti_second_weekend.short_liquidations_usd"
            )
        )
        self.long_liquidations = float(
            self.engine.evidence.value(
                "events.wti_second_weekend.long_liquidations_usd"
            )
        )
        wti_spec = {spec.symbol: spec for spec in self.engine.market_specs()}[
            "WTIOIL"
        ]
        self.venue_reference = self.observed_mark / (1.0 + wti_spec.band_rate)

    def test_static_band_ceiling(self) -> None:
        self.assertTrue(self.mark_is_upper_bound)
        self.assertNotAlmostEqual(self.venue_reference, self.cme_close, places=3)
        machine = machine_for_market(
            self.engine.evidence,
            "WTIOIL",
            reference_price=self.venue_reference,
            reset_limit=0,
        )
        self.assertAlmostEqual(
            machine.theoretical_hard_cap("up"), self.observed_mark, places=9
        )

    def test_reanchored_ceiling(self) -> None:
        machine = machine_for_market(
            self.engine.evidence, "WTIOIL", reference_price=self.venue_reference
        )
        self.assertAlmostEqual(
            machine.theoretical_hard_cap("up"), 105.6558825, places=7
        )

    def test_reopen_exceeds_even_the_counterfactual_ceiling(self) -> None:
        machine = machine_for_market(
            self.engine.evidence, "WTIOIL", reference_price=self.venue_reference
        )
        self.assertGreater(self.reopen, machine.theoretical_hard_cap("up"))

    def test_reanchor_was_not_live_during_the_event(self) -> None:
        self.assertFalse(
            bool(
                self.engine.evidence.value(
                    "events.wti_second_weekend.reanchor_active_during_event"
                )
            )
        )

    def test_external_reopen_recognition_gap_is_12_10_percentage_points(self) -> None:
        recognition_gap = (self.reopen - self.observed_mark) / self.cme_close
        self.assertAlmostEqual(recognition_gap, 0.121040, places=6)

    def test_liquidation_imbalance_is_observed_context_not_attack_profit(self) -> None:
        self.assertEqual(self.short_liquidations, 36_900_000.0)
        self.assertEqual(self.long_liquidations, 2_100_000.0)
        self.assertAlmostEqual(
            self.short_liquidations / self.long_liquidations,
            17.5714285714,
            places=8,
        )


class BoundaryTests(unittest.TestCase):
    """T5: reset budgets, exact trigger touches, and rejected inputs."""

    def test_exact_trigger_touch_consumes_a_reset(self) -> None:
        machine = DiscoveryBoundMachine(
            reference_price=100.0, band_rate=0.05, reset_limit=1
        )
        step = machine.step(100.0 * (1.0 + 0.05 * 0.90))
        self.assertEqual(step.trigger_direction, "up")
        self.assertEqual(step.upward_resets_used, 1)

    def test_just_below_the_trigger_does_not_consume_a_reset(self) -> None:
        machine = DiscoveryBoundMachine(
            reference_price=100.0, band_rate=0.05, reset_limit=1
        )
        step = machine.step(100.0 * (1.0 + 0.05 * 0.90) - 1e-6)
        self.assertEqual(step.trigger_direction, "none")
        self.assertEqual(step.upward_resets_used, 0)

    def test_exhausted_budget_stops_at_the_hard_cap(self) -> None:
        machine = DiscoveryBoundMachine(
            reference_price=100.0, band_rate=0.05, reset_limit=2
        )
        steps = machine.process([1_000.0] * 10)
        self.assertAlmostEqual(steps[-1].effective_mark_price, 115.7625, places=4)
        self.assertEqual(steps[-1].upward_resets_used, 2)

    def test_invalid_construction_is_rejected(self) -> None:
        for kwargs in (
            dict(reference_price=0.0, band_rate=0.05, reset_limit=2),
            dict(reference_price=100.0, band_rate=0.0, reset_limit=2),
            dict(reference_price=100.0, band_rate=1.0, reset_limit=2),
            dict(reference_price=100.0, band_rate=0.05, reset_limit=-1),
            dict(
                reference_price=100.0,
                band_rate=0.05,
                reset_limit=2,
                trigger_fraction=0.0,
            ),
            dict(reference_price=float("nan"), band_rate=0.05, reset_limit=2),
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    DiscoveryBoundMachine(**kwargs)

    def test_non_finite_price_is_rejected(self) -> None:
        machine = DiscoveryBoundMachine(
            reference_price=100.0, band_rate=0.05, reset_limit=2
        )
        for bad in (float("nan"), float("inf"), 0.0, -1.0):
            with self.subTest(price=bad):
                with self.assertRaises(ValueError):
                    machine.step(bad)


if __name__ == "__main__":
    unittest.main()
