from __future__ import annotations

import unittest

from rwa_market_gap.commodity_oracle.margin import (
    ADLCandidate,
    allocate_adl,
    assert_matched_notional,
    limited_liability_loss,
    liquidation_adverse_move,
    loss_path,
    maintenance_margin_rate,
)


class MarginFormulaTests(unittest.TestCase):
    def test_maintenance_margin_uses_maximum_not_chosen_leverage(self) -> None:
        self.assertAlmostEqual(maintenance_margin_rate(20.0, 0.5), 0.025)
        self.assertAlmostEqual(
            liquidation_adverse_move(
                chosen_leverage=20.0,
                max_leverage=20.0,
                maintenance_margin_fraction=0.5,
            ),
            0.025,
        )
        self.assertAlmostEqual(
            liquidation_adverse_move(
                chosen_leverage=10.0,
                max_leverage=20.0,
                maintenance_margin_fraction=0.5,
            ),
            0.075,
        )
        self.assertAlmostEqual(
            liquidation_adverse_move(
                chosen_leverage=5.0,
                max_leverage=20.0,
                maintenance_margin_fraction=0.5,
            ),
            0.175,
        )

    def test_margin_mode_changes_loss_waterfall(self) -> None:
        self.assertEqual(
            loss_path("cross"),
            ("market_liquidation", "backstop_liquidator", "adl"),
        )
        self.assertEqual(loss_path("isolated"), ("market_liquidation", "adl"))

    def test_limited_liability_caps_trader_loss_at_margin(self) -> None:
        result = limited_liability_loss(
            notional_usd=20_000_000.0,
            chosen_leverage=20.0,
            adverse_move=0.1701,
        )
        self.assertAlmostEqual(result.initial_margin_usd, 1_000_000.0)
        self.assertAlmostEqual(result.true_loss_usd, 3_402_000.0)
        self.assertAlmostEqual(result.trader_borne_loss_usd, 1_000_000.0)
        self.assertAlmostEqual(result.deficit_usd, 2_402_000.0)


class ADLInvariantTests(unittest.TestCase):
    def test_adl_uses_documented_rank_and_conserves_deficit(self) -> None:
        high_rank = ADLCandidate(
            account_id="high-rank",
            contracts=1_000.0,
            entry_price=80.0,
            mark_price=95.0,
            account_value_usd=10_000.0,
            fair_price=105.0,
        )
        low_rank = ADLCandidate(
            account_id="low-rank",
            contracts=1_000.0,
            entry_price=90.0,
            mark_price=95.0,
            account_value_usd=50_000.0,
            fair_price=105.0,
        )
        allocation = allocate_adl(12_000.0, (low_rank, high_rank))

        self.assertEqual(allocation.actions[0].account_id, "high-rank")
        self.assertAlmostEqual(
            allocation.allocated_deficit_usd + allocation.remaining_deficit_usd,
            allocation.requested_deficit_usd,
        )
        self.assertTrue(all(action.contracts_closed >= 0.0 for action in allocation.actions))

    def test_perpetual_long_and_short_notional_must_match(self) -> None:
        assert_matched_notional((5_000.0, 5_000.0), (10_000.0,))
        with self.assertRaises(AssertionError):
            assert_matched_notional((10_000.0,), (9_999.0,))


if __name__ == "__main__":
    unittest.main()
