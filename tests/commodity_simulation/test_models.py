from __future__ import annotations

from copy import deepcopy
from dataclasses import MISSING, fields, replace
from datetime import date
from math import nan
import unittest

from rwa_market_gap.commodity_simulation.evidence import VerifiedInputLedger
from rwa_market_gap.commodity_simulation import (
    CommoditySimulationEngine,
)
from rwa_market_gap.commodity_simulation.common import (
    EconomicLedger,
    UnsupportedModel,
)
from rwa_market_gap.commodity_simulation.execution import (
    PowerLawAverageImpactCurve,
)
from rwa_market_gap.commodity_simulation.gold import (
    GoldFalsificationResult,
)
from rwa_market_gap.commodity_simulation.natural_gas import (
    NaturalGasEvidenceReview,
)
from rwa_market_gap.commodity_simulation.oracle_math import (
    minimum_compounded_updates,
)
from rwa_market_gap.commodity_simulation.sensitivity import (
    GOLD_ASSUMPTION_MAP,
    WTI_ASSUMPTION_MAP,
    gold_one_at_a_time,
    wti_one_at_a_time,
)
from rwa_market_gap.commodity_simulation.wti import (
    WTIStressAssumptions,
    WTIStressEconomics,
)


class CommodityWTITests(unittest.TestCase):
    def setUp(self) -> None:
        self.suite = CommoditySimulationEngine().build()

    def test_observed_returns_use_entry_mark_denominator(self) -> None:
        first, second = self.suite.wti.analyze_all()
        self.assertAlmostEqual(first.position_return_rate, (75.0 - 70.64) / 70.64)
        self.assertAlmostEqual(
            second.position_return_rate, (106.89 - 95.833) / 95.833
        )
        self.assertAlmostEqual(
            second.price_recognition_gap_rate, (106.89 - 95.833) / 91.35
        )
        self.assertAlmostEqual(
            second.signed_price_recognition_gap_rate,
            (106.89 - 95.833) / 91.35,
        )

    def test_no_success_probability_is_manufactured(self) -> None:
        result = self.suite.wti.analyze("wti_second_weekend")
        self.assertIsNone(result.success_probability)
        self.assertAlmostEqual(result.direction_match_observation, 0.899)

    def test_capacity_prevents_linear_notional_extrapolation(self) -> None:
        base = self.suite.wti.analyze("wti_second_weekend")
        oversized = self.suite.wti.with_requested_notional(10_000_000).analyze(
            "wti_second_weekend"
        )
        self.assertTrue(oversized.capacity.capacity_constrained)
        self.assertEqual(
            oversized.capacity.executable_notional_usd,
            base.capacity.executable_notional_usd,
        )
        self.assertEqual(oversized.ledger.net_profit_usd, base.ledger.net_profit_usd)

    def test_slippage_cost_is_size_dependent_below_capacity(self) -> None:
        small = self.suite.wti.with_requested_notional(100_000).analyze(
            "wti_second_weekend"
        )
        full = self.suite.wti.with_requested_notional(1_000_000).analyze(
            "wti_second_weekend"
        )
        self.assertAlmostEqual(small.realized_round_trip_slippage_rate, 0.0001)
        self.assertAlmostEqual(full.realized_round_trip_slippage_rate, 0.001)
        small_slippage = (
            small.capacity.executable_notional_usd
            * small.realized_round_trip_slippage_rate
        )
        full_slippage = (
            full.capacity.executable_notional_usd
            * full.realized_round_trip_slippage_rate
        )
        self.assertNotAlmostEqual(full_slippage, 10.0 * small_slippage)

    def test_slippage_curve_shape_changes_partial_capacity_execution(self) -> None:
        base_assumptions = replace(
            self.suite.wti.assumptions,
            requested_notional_usd=500_000,
        )
        shallow = WTIStressEconomics(
            self.suite.wti.evidence,
            replace(base_assumptions, slippage_exponent=0.5),
        ).analyze("wti_second_weekend")
        steep = WTIStressEconomics(
            self.suite.wti.evidence,
            replace(base_assumptions, slippage_exponent=2.0),
        ).analyze("wti_second_weekend")
        self.assertGreater(
            shallow.realized_round_trip_slippage_rate,
            steep.realized_round_trip_slippage_rate,
        )
        self.assertLess(shallow.ledger.net_profit_usd, steep.ledger.net_profit_usd)

    def test_equal_mark_has_no_directional_signal(self) -> None:
        result = self.suite.wti.analyze_prices(
            event="no_signal",
            friday_close_usd=100.0,
            onchain_entry_mark_usd=100.0,
            external_reopen_usd=90.0,
        )
        self.assertIsInstance(result, UnsupportedModel)
        assert isinstance(result, UnsupportedModel)
        self.assertIn("no trading signal", result.reason)

    def test_adverse_path_is_not_priced_without_execution_evidence(self) -> None:
        result = self.suite.wti.analyze_prices(
            event="hypothetical_adverse_path",
            friday_close_usd=100.0,
            onchain_entry_mark_usd=105.0,
            external_reopen_usd=90.0,
        )
        self.assertIsInstance(result, UnsupportedModel)
        assert isinstance(result, UnsupportedModel)
        self.assertIn("does not fabricate", result.reason)

    def test_negative_funding_is_a_receipt_not_a_negative_cost(self) -> None:
        assumptions = replace(
            self.suite.wti.assumptions,
            signed_funding_rate_over_horizon=-0.005,
        )
        model = WTIStressEconomics(self.suite.wti.evidence, assumptions)
        result = model.analyze("wti_second_weekend")
        baseline = self.suite.wti.analyze("wti_second_weekend")
        self.assertGreater(result.ledger.pfc_usd, baseline.ledger.pfc_usd)
        self.assertLess(result.ledger.coc_usd, baseline.ledger.coc_usd)

    def _with_funding(self, rate: float) -> WTIStressEconomics:
        return WTIStressEconomics(
            self.suite.wti.evidence,
            replace(
                self.suite.wti.assumptions,
                signed_funding_rate_over_horizon=rate,
                funding_sensitivity_low=min(
                    self.suite.wti.assumptions.funding_sensitivity_low, rate
                ),
                funding_sensitivity_high=max(
                    self.suite.wti.assumptions.funding_sensitivity_high, rate
                ),
            ),
        )

    def test_net_profit_is_zero_at_the_break_even_funding_rate(self) -> None:
        base = self.suite.wti.analyze("wti_second_weekend")
        at_break_even = self._with_funding(
            base.break_even_funding_rate_over_horizon
        ).analyze("wti_second_weekend")
        self.assertAlmostEqual(at_break_even.ledger.net_profit_usd, 0.0, places=6)

    def test_funding_above_break_even_flips_the_sign(self) -> None:
        base = self.suite.wti.analyze("wti_second_weekend")
        just_above = self._with_funding(
            base.break_even_funding_rate_over_horizon + 0.001
        ).analyze("wti_second_weekend")
        just_below = self._with_funding(
            base.break_even_funding_rate_over_horizon - 0.001
        ).analyze("wti_second_weekend")
        self.assertLess(just_above.ledger.net_profit_usd, 0.0)
        self.assertGreater(just_below.ledger.net_profit_usd, 0.0)

    def test_break_even_funding_does_not_depend_on_the_assumed_funding(self) -> None:
        # The break-even level is a property of the observed state, not of the
        # C-grade funding placeholder, so every assumed rate must yield the same
        # threshold.
        thresholds = {
            round(
                self._with_funding(rate)
                .analyze("wti_second_weekend")
                .break_even_funding_rate_over_horizon,
                12,
            )
            for rate in (-0.005, 0.0, 0.0005, 0.005)
        }
        self.assertEqual(len(thresholds), 1)

    def test_break_even_funding_exceeds_the_declared_sensitivity_ceiling(self) -> None:
        # The research finding: the assumption interval cannot reach the level
        # that would neutralise the observed state, so the sweep alone can never
        # overturn the conclusion.
        engine = CommoditySimulationEngine()
        _, ceiling = engine.assumptions.record(
            "wti.signed_funding_rate_over_horizon"
        ).sensitivity
        result = engine.build().wti.analyze("wti_second_weekend")
        self.assertGreater(result.break_even_funding_rate_over_horizon, ceiling)
        self.assertAlmostEqual(
            result.break_even_funding_rate_over_horizon, 0.11334982, places=6
        )
        self.assertAlmostEqual(
            result.simple_average_break_even_funding_rate_per_hour,
            result.break_even_funding_rate_over_horizon / 49.0,
        )
        self.assertFalse(result.break_even_funding_within_declared_sensitivity)

    def test_nan_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.suite.wti.analyze_prices(
                event="bad",
                friday_close_usd=nan,
                onchain_entry_mark_usd=100.0,
                external_reopen_usd=101.0,
            )


class CommodityGoldTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gold = CommoditySimulationEngine().build().gold

    def test_zero_cost_structural_break_even_is_one_minus_ltv(self) -> None:
        result = self.gold.analyze()
        self.assertIsInstance(result, GoldFalsificationResult)
        assert isinstance(result, GoldFalsificationResult)
        self.assertAlmostEqual(result.structural_zero_cost_break_even_discount, 0.30)

    def test_observed_divergence_used_as_discount_is_unprofitable(self) -> None:
        for exponent in (0.5, 1.0, 2.0):
            result = self.gold.with_impact_exponent(exponent).analyze()
            assert isinstance(result, GoldFalsificationResult)
            self.assertFalse(result.profitable_at_tested_discount)
            self.assertIn("discount assumption", result.tested_discount_source)
            self.assertGreater(
                result.modelled_break_even_discount,
                result.tested_discount_assumption,
            )

    def test_market_impact_depends_on_position_size(self) -> None:
        full = self.gold.analyze()
        smaller_model = type(self.gold)(
            self.gold.evidence,
            replace(self.gold.assumptions, requested_borrow_usd=300_000),
        )
        small = smaller_model.analyze()
        assert isinstance(full, GoldFalsificationResult)
        assert isinstance(small, GoldFalsificationResult)
        self.assertGreater(full.terminal_price_impact, small.terminal_price_impact)
        self.assertGreater(
            full.reference_liquidity_utilization,
            small.reference_liquidity_utilization,
        )

    def test_reported_bound_is_used_as_average_impact_proxy(self) -> None:
        curve = PowerLawAverageImpactCurve(
            reference_quantity=2_800.0,
            average_impact_at_reference=0.06,
            exponent=1.0,
        )
        self.assertAlmostEqual(curve.average_slippage(2_800.0), 0.06)
        self.assertAlmostEqual(curve.terminal_impact(2_800.0), 0.12)

    def test_modelled_gold_break_even_zeroes_net_profit(self) -> None:
        base = self.gold.analyze()
        assert isinstance(base, GoldFalsificationResult)
        at_break_even = self.gold.analyze(
            token_discount=base.modelled_break_even_discount
        )
        assert isinstance(at_break_even, GoldFalsificationResult)
        self.assertAlmostEqual(at_break_even.ledger.net_profit_usd, 0.0, places=6)

    def test_sell_side_liquidity_is_explicitly_labelled_as_proxy(self) -> None:
        result = self.gold.analyze()
        assert isinstance(result, GoldFalsificationResult)
        self.assertTrue(result.uses_opposite_side_liquidity_proxy)
        self.assertEqual(result.observed_liquidity_side, "sell XAUt for USDC")
        self.assertEqual(result.modelled_execution_side, "buy XAUt collateral")

    def test_non_stale_state_is_explicitly_unsupported(self) -> None:
        result = self.gold.analyze(stale_oracle_available=False)
        self.assertEqual(result.name, "gold stale-collateral attempt")
        self.assertIn("no defined overvaluation", result.reason)

    def test_gold_probability_is_not_fabricated(self) -> None:
        result = self.gold.analyze()
        assert isinstance(result, GoldFalsificationResult)
        self.assertIsNone(result.success_probability)


class CommodityNaturalGasTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gas = CommoditySimulationEngine().build().natural_gas

    def test_missing_event_window_blocks_dollar_loss(self) -> None:
        result = self.gas.analyze()
        self.assertFalse(result.event_window_verified)
        self.assertIsNone(result.aligned_tracking_error_usd)
        self.assertIsNone(result.attack_success_probability)

    def test_notional_without_event_window_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.gas.analyze(exposure_notional_usd=1_000_000)

    def test_explicit_aligned_window_allows_illustrative_error(self) -> None:
        engine = CommoditySimulationEngine()
        payload = deepcopy(engine.evidence.payload)
        event = payload["events"]["natural_gas_benchmark_gap"]
        event["event_window_start"] = {
            "value": "2026-03-01",
            "unit": "ISO date",
            "definition": "Verified start of the aligned benchmark window.",
            "grade": "B",
            "source": "Time-aligned event reconstruction",
            "as_of": "2026-04-13",
        }
        event["event_window_end"] = {
            "value": "2026-04-13",
            "unit": "ISO date",
            "definition": "Verified end of the aligned benchmark window.",
            "grade": "B",
            "source": "Time-aligned event reconstruction",
            "as_of": "2026-04-13",
        }
        evidence = VerifiedInputLedger(
            payload, source_path=engine.evidence.source_path
        )
        result = NaturalGasEvidenceReview(evidence).analyze(
            exposure_notional_usd=1_000_000
        )
        self.assertTrue(result.event_window_verified)
        self.assertEqual(result.event_window_start, date(2026, 3, 1))
        self.assertEqual(result.event_window_end, date(2026, 4, 13))
        self.assertAlmostEqual(result.aligned_tracking_error_usd, 919_000)

    def test_caller_dates_cannot_self_verify_the_event_window(self) -> None:
        with self.assertRaises(TypeError):
            self.gas.analyze(
                event_window_start=date(1900, 1, 1),  # type: ignore[call-arg]
                event_window_end=date(1900, 1, 1),  # type: ignore[call-arg]
            )


class CommodityMathAndAccountingTests(unittest.TestCase):
    def test_compounded_clamp_requires_23_not_25_updates(self) -> None:
        self.assertEqual(minimum_compounded_updates(1.0, 1.12104, 0.005), 23)

    def test_accounting_identity(self) -> None:
        ledger = EconomicLedger(pfc_usd=100.0, coc_usd=30.0, capital_at_risk_usd=50.0)
        self.assertEqual(ledger.net_profit_usd, 70.0)

    def test_every_assumption_has_a_sensitivity_sweep(self) -> None:
        engine = CommoditySimulationEngine()
        suite = engine.build()
        paths = {record.path for record in engine.assumptions.records}
        self.assertEqual(paths, set(WTI_ASSUMPTION_MAP) | set(GOLD_ASSUMPTION_MAP))
        self.assertEqual(
            len(wti_one_at_a_time(suite.wti, engine.assumptions)),
            3 * len(WTI_ASSUMPTION_MAP),
        )
        self.assertEqual(
            len(gold_one_at_a_time(suite.gold, engine.assumptions)),
            3 * len(GOLD_ASSUMPTION_MAP),
        )


class CommodityProvenanceAndSweepTests(unittest.TestCase):
    """R-5 of the verification protocol: no hardcoded economic parameters."""

    def test_horizon_hours_has_no_code_side_default(self) -> None:
        field = {item.name: item for item in fields(WTIStressAssumptions)}[
            "horizon_hours"
        ]
        self.assertIs(field.default, MISSING)
        self.assertIs(field.default_factory, MISSING)

    def test_horizon_hours_is_read_from_grade_a_evidence(self) -> None:
        engine = CommoditySimulationEngine()
        record = engine.evidence.record(
            "market_sessions.standard_weekend_closure_hours"
        )
        self.assertEqual(record.grade, "A")
        self.assertEqual(
            engine.build().wti.assumptions.horizon_hours, float(record.value)
        )

    def test_gold_impact_reference_is_read_from_the_ledger(self) -> None:
        engine = CommoditySimulationEngine()
        record = engine.evidence.record(
            "gold_collateral.disposal_capacity_average_price_impact_bound"
        )
        self.assertEqual(record.grade, "B")
        base = engine.build().gold.analyze()
        assert isinstance(base, GoldFalsificationResult)

        payload = deepcopy(engine.evidence.payload)
        payload["gold_collateral"][
            "disposal_capacity_average_price_impact_bound"
        ]["value"] = 2.0 * float(record.value)
        doubled = CommoditySimulationEngine(
            evidence=VerifiedInputLedger(
                payload, source_path=engine.evidence.source_path
            )
        )
        result = doubled.build().gold.analyze()
        assert isinstance(result, GoldFalsificationResult)
        self.assertAlmostEqual(
            result.terminal_price_impact, 2.0 * base.terminal_price_impact
        )

    def test_flat_sweep_rows_always_carry_an_explanation(self) -> None:
        # A flat row with no reason would read as "this assumption is
        # irrelevant", which is a different claim from "inactive here".
        engine = CommoditySimulationEngine()
        suite = engine.build()
        grouped: dict[str, list] = {}
        for point in wti_one_at_a_time(suite.wti, engine.assumptions):
            grouped.setdefault(point.parameter, []).append(point)
        flat = {
            parameter: rows
            for parameter, rows in grouped.items()
            if len({row.net_profit_usd for row in rows}) == 1
        }
        self.assertTrue(flat, "expected at least one inactive parameter")
        for parameter, rows in flat.items():
            self.assertTrue(
                all(row.inactive_reason for row in rows),
                f"{parameter} is flat but carries no explanation",
            )

    def test_slippage_exponent_is_active_below_capacity(self) -> None:
        # Proves the flat sweep row is a property of the configuration, not of
        # the parameter.
        suite = CommoditySimulationEngine().build()
        half = replace(suite.wti.assumptions, requested_notional_usd=500_000)
        shallow = WTIStressEconomics(
            suite.wti.evidence, replace(half, slippage_exponent=0.5)
        ).analyze("wti_second_weekend")
        steep = WTIStressEconomics(
            suite.wti.evidence, replace(half, slippage_exponent=2.0)
        ).analyze("wti_second_weekend")
        self.assertNotEqual(
            shallow.ledger.net_profit_usd, steep.ledger.net_profit_usd
        )


if __name__ == "__main__":
    unittest.main()
