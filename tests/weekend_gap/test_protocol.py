from __future__ import annotations

import unittest
from dataclasses import replace
from statistics import fmean

from rwa_market_gap.weekend_gap.protocol_config import (
    DEFAULT_PROTOCOL_AWARE_WEEKEND_GAP_CONFIG,
    EvidenceConfig,
)
from rwa_market_gap.weekend_gap.protocol import ProtocolAwareWeekendGapEngine


def enabled_config():
    base = DEFAULT_PROTOCOL_AWARE_WEEKEND_GAP_CONFIG
    return replace(
        base,
        oracle=replace(
            base.oracle,
            allow_new_loans_when_market_closed=True,
            closed_market_staleness_exemption=True,
        ),
    )


class ProtocolAwareOriginationTests(unittest.TestCase):
    def test_guarded_default_blocks_unverified_closed_market_loan(self) -> None:
        engine = ProtocolAwareWeekendGapEngine()
        decision = engine.origination_decision()
        outcome = engine.realized(0.35)

        self.assertFalse(decision.allowed)
        self.assertIn("closed-market new loans are disabled", decision.blocking_reasons)
        self.assertEqual(outcome.attacker_net_profit_vs_hold_usd, 0.0)
        self.assertEqual(outcome.protocol_bad_debt_usd, 0.0)

    def test_stale_price_needs_explicit_closed_market_exemption(self) -> None:
        base = DEFAULT_PROTOCOL_AWARE_WEEKEND_GAP_CONFIG
        config = replace(
            base,
            oracle=replace(
                base.oracle,
                allow_new_loans_when_market_closed=True,
                closed_market_staleness_exemption=False,
            ),
        )

        decision = ProtocolAwareWeekendGapEngine(config).origination_decision()

        self.assertFalse(decision.allowed)
        self.assertIn(
            "closed-market oracle price is too old for a new loan",
            decision.blocking_reasons,
        )

    def test_closed_market_price_outside_band_is_blocked(self) -> None:
        base = enabled_config()
        config = replace(
            base,
            oracle=replace(
                base.oracle,
                oracle_price_usd=106.0,
                closed_market_price_band_rate=0.05,
            ),
        )

        decision = ProtocolAwareWeekendGapEngine(config).origination_decision()

        self.assertFalse(decision.allowed)
        self.assertIn(
            "oracle price is outside the closed-market price band",
            decision.blocking_reasons,
        )

    def test_borrow_is_bounded_by_liquidity_cap_and_borrow_factor(self) -> None:
        base = enabled_config()
        constrained = replace(
            base,
            reserve=replace(
                base.reserve,
                debt_borrow_factor=2.0,
                debt_reserve_total_supply_usd=10_500_000.0,
                debt_reserve_current_borrowed_usd=10_000_000.0,
                debt_borrow_cap_usd=10_400_000.0,
            ),
        )

        decision = ProtocolAwareWeekendGapEngine(constrained).origination_decision()

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.ltv_borrow_capacity_usd, 350_000.0)
        self.assertEqual(decision.available_debt_liquidity_usd, 500_000.0)
        self.assertEqual(decision.remaining_debt_borrow_cap_usd, 400_000.0)
        self.assertEqual(decision.borrowed_principal_usd, 350_000.0)

    def test_supply_cap_blocks_the_requested_position(self) -> None:
        base = enabled_config()
        config = replace(
            base,
            reserve=replace(
                base.reserve,
                collateral_supply_cap_usd=5_500_000.0,
                collateral_supplied_before_attack_usd=5_000_000.0,
            ),
        )

        decision = ProtocolAwareWeekendGapEngine(config).origination_decision()

        self.assertFalse(decision.allowed)
        self.assertIn(
            "requested collateral exceeds the remaining supply cap",
            decision.blocking_reasons,
        )

    def test_liquidation_and_insolvency_thresholds_are_distinct(self) -> None:
        decision = ProtocolAwareWeekendGapEngine(
            enabled_config()
        ).origination_decision()

        self.assertLess(
            decision.liquidation_start_gap,
            decision.principal_insolvency_gap,
        )
        self.assertAlmostEqual(decision.liquidation_start_gap, 0.1246, places=3)
        self.assertAlmostEqual(decision.principal_insolvency_gap, 0.2997, places=3)


class ProtocolAwarePricingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = ProtocolAwareWeekendGapEngine(enabled_config())

    def test_utilization_curve_increases_and_reaches_configured_points(self) -> None:
        self.assertAlmostEqual(self.engine.annual_borrow_rate(0.0), 0.02)
        self.assertAlmostEqual(self.engine.annual_borrow_rate(0.80), 0.10)
        self.assertAlmostEqual(self.engine.annual_borrow_rate(1.0), 1.00)
        self.assertGreater(
            self.engine.annual_borrow_rate(0.90),
            self.engine.annual_borrow_rate(0.70),
        )

    def test_cpmm_uses_separate_asset_and_stable_reserves_with_fee(self) -> None:
        liquidity = self.engine.config.liquidity
        effective_input = 10_000.0 * (1.0 - liquidity.swap_fee_rate)
        expected = (
            liquidity.stable_reserve_usd
            * effective_input
            / (liquidity.asset_reserve_units + effective_input)
        )

        self.assertAlmostEqual(self.engine.amm_sale_proceeds_usd(), expected)

    def test_captured_aggregator_quote_overrides_cpmm(self) -> None:
        base = enabled_config()
        config = replace(
            base,
            liquidity=replace(
                base.liquidity,
                aggregator_quote_for_full_position_usd=812_345.0,
                quote_label="captured quote fixture",
            ),
        )

        proceeds = ProtocolAwareWeekendGapEngine(config).amm_sale_proceeds_usd()

        self.assertEqual(proceeds, 812_345.0)

    def test_default_illustration_still_does_not_prefer_borrowing(self) -> None:
        outcome = self.engine.realized(0.35)

        self.assertLess(outcome.borrow_minus_sale_usd, 0.0)


class ProtocolAwareLiquidationTests(unittest.TestCase):
    def test_liquidation_is_partial_not_an_immediate_full_wipeout(self) -> None:
        base = enabled_config()
        config = replace(
            base,
            liquidation=replace(
                base.liquidation,
                minimum_bonus=0.001,
                maximum_bonus=0.001,
                bonus_ramp_hours=0.0,
                collateral_sale_slippage_rate=0.0,
                execution_cost_per_round_usd=0.0,
            ),
        )
        engine = ProtocolAwareWeekendGapEngine(config)

        outcome = engine.realized(0.20)
        first = outcome.liquidation.executed_rounds[0]

        self.assertTrue(outcome.liquidation.initially_liquidatable)
        self.assertAlmostEqual(
            first.debt_repaid_usd,
            outcome.origination.debt_at_market_reopen_usd * 0.10,
        )
        self.assertLess(
            first.debt_repaid_usd,
            outcome.origination.debt_at_market_reopen_usd,
        )
        self.assertFalse(outcome.strategically_defaults)

    def test_liquidator_waits_until_dynamic_bonus_covers_execution(self) -> None:
        engine = ProtocolAwareWeekendGapEngine(enabled_config())

        outcome = engine.realized(0.20)

        self.assertIsNotNone(outcome.liquidation.first_execution_seconds)
        self.assertGreater(outcome.liquidation.first_execution_seconds, 0.0)
        self.assertGreater(
            outcome.liquidation.executed_rounds[0].bonus_rate,
            engine.config.liquidation.minimum_bonus,
        )

    def test_large_gap_can_create_strategic_default_and_bad_debt(self) -> None:
        outcome = ProtocolAwareWeekendGapEngine(enabled_config()).realized(0.35)

        self.assertTrue(outcome.strategically_defaults)
        self.assertGreater(outcome.attacker_net_profit_vs_hold_usd, 0.0)
        self.assertGreater(outcome.protocol_bad_debt_usd, 0.0)

    def test_upward_gap_is_supported_and_repaid(self) -> None:
        outcome = ProtocolAwareWeekendGapEngine(enabled_config()).realized(-0.10)

        self.assertFalse(outcome.liquidation.initially_liquidatable)
        self.assertFalse(outcome.strategically_defaults)
        expected_loss = -(
            outcome.origination.accrued_interest_usd
            + outcome.direct_attacker_cost_usd
        )
        self.assertAlmostEqual(
            outcome.attacker_net_profit_vs_hold_usd,
            expected_loss,
        )

    def test_impossible_drop_below_zero_price_is_rejected(self) -> None:
        engine = ProtocolAwareWeekendGapEngine(enabled_config())

        with self.assertRaises(ValueError):
            engine.realized(1.01)


class ProtocolAwareGapDatasetTests(unittest.TestCase):
    def test_complete_sample_distribution_drives_expected_values(self) -> None:
        engine = ProtocolAwareWeekendGapEngine(enabled_config())
        gaps = (-0.10, 0.00, 0.10, 0.20, 0.35)

        summary = engine.evaluate_gap_samples(
            gaps,
            sample_source="synthetic unit-test fixture",
        )

        self.assertEqual(summary.sample_size, len(gaps))
        self.assertAlmostEqual(summary.mean_gap, fmean(gaps))
        self.assertAlmostEqual(
            summary.expected_attacker_net_profit_usd,
            fmean(o.attacker_net_profit_vs_hold_usd for o in summary.outcomes),
        )
        self.assertAlmostEqual(
            summary.expected_protocol_bad_debt_usd,
            fmean(o.protocol_bad_debt_usd for o in summary.outcomes),
        )
        self.assertFalse(summary.empirically_calibrated)

    def test_verified_label_requires_sources_and_all_evidence_flags(self) -> None:
        with self.assertRaises(ValueError):
            EvidenceConfig(protocol_parameters_verified=True)

        base = enabled_config()
        verified = replace(
            base,
            evidence=EvidenceConfig(
                protocol_parameters_verified=True,
                oracle_policy_verified=True,
                liquidity_snapshot_verified=True,
                gap_dataset_verified=True,
                source_notes=("reproducible fixture source",),
            ),
        )
        summary = ProtocolAwareWeekendGapEngine(verified).evaluate_gap_samples(
            (0.0, 0.35),
            sample_source="verified fixture",
        )

        self.assertTrue(summary.empirically_calibrated)

    def test_empty_gap_dataset_is_rejected(self) -> None:
        engine = ProtocolAwareWeekendGapEngine(enabled_config())

        with self.assertRaises(ValueError):
            engine.evaluate_gap_samples((), sample_source="empty fixture")


if __name__ == "__main__":
    unittest.main()
