from __future__ import annotations

import unittest

from rwa_market_gap.commodity_oracle.discovery_bound import (
    DiscoveryBoundMachine,
    OracleUpdateClamp,
)
from rwa_market_gap.commodity_oracle.evidence import VerifiedInputLedger
from rwa_market_gap.commodity_oracle.models import MarketSpec


class DiscoveryBoundIdentityTests(unittest.TestCase):
    def test_band_equals_inverse_max_leverage_for_all_five_markets(self) -> None:
        ledger = VerifiedInputLedger.load()
        for symbol in ("GOLD", "WTIOIL", "NATGAS", "SILVER", "BRENTOIL"):
            market = MarketSpec.from_ledger(ledger, symbol)
            self.assertAlmostEqual(market.band_identity_error, 0.0, places=12)

    def test_published_wti_monotone_caps_are_reproduced(self) -> None:
        upward = DiscoveryBoundMachine(
            reference_price=100.0,
            band_rate=0.05,
            reset_limit=2,
        )
        downward = DiscoveryBoundMachine(
            reference_price=100.0,
            band_rate=0.05,
            reset_limit=2,
        )

        up_steps = upward.process((200.0, 200.0, 200.0))
        down_steps = downward.process((1.0, 1.0, 1.0))

        self.assertAlmostEqual(up_steps[-1].effective_mark_price, 115.7625)
        self.assertAlmostEqual(down_steps[-1].effective_mark_price, 85.7375)


class DiscoveryBoundStateTests(unittest.TestCase):
    def test_same_final_input_has_different_mark_after_sawtooth_path(self) -> None:
        monotone = DiscoveryBoundMachine(
            reference_price=100.0, band_rate=0.05, reset_limit=2
        )
        sawtooth = DiscoveryBoundMachine(
            reference_price=100.0, band_rate=0.05, reset_limit=2
        )

        monotone_mark = monotone.process((105.0, 110.25, 112.0))[-1]
        sawtooth_mark = sawtooth.process((95.0, 104.0, 110.0, 112.0))[-1]

        self.assertAlmostEqual(monotone_mark.effective_mark_price, 112.0)
        self.assertAlmostEqual(sawtooth_mark.effective_mark_price, 109.974375)
        self.assertEqual(sawtooth_mark.upward_resets_used, 2)
        self.assertEqual(sawtooth_mark.downward_resets_used, 1)

    def test_directional_reset_counters_are_independent(self) -> None:
        machine = DiscoveryBoundMachine(
            reference_price=100.0, band_rate=0.05, reset_limit=2
        )
        machine.process((105.0, 110.25, 95.0))
        self.assertEqual(machine.upward_resets_used, 2)
        self.assertEqual(machine.downward_resets_used, 1)

    def test_exact_trigger_updates_reference(self) -> None:
        machine = DiscoveryBoundMachine(
            reference_price=100.0,
            band_rate=0.05,
            reset_limit=2,
            trigger_fraction=0.90,
        )
        step = machine.step(104.5)
        self.assertEqual(step.trigger_direction, "up")
        self.assertAlmostEqual(step.reference_after, 105.0)

    def test_external_session_reset_clears_both_counters(self) -> None:
        machine = DiscoveryBoundMachine(
            reference_price=100.0, band_rate=0.05, reset_limit=2
        )
        machine.process((105.0, 95.0))
        machine.reset_for_external_session(106.89)
        self.assertEqual(machine.upward_resets_used, 0)
        self.assertEqual(machine.downward_resets_used, 0)
        self.assertAlmostEqual(machine.reference_price, 106.89)

    def test_relayer_clamp_is_binding_and_requires_25_reference_steps(self) -> None:
        clamp = OracleUpdateClamp(protocol_rate=0.01, relayer_rate=0.005)
        self.assertAlmostEqual(clamp.binding_rate, 0.005)
        self.assertAlmostEqual(clamp.apply_once(100.0, 120.0), 100.5)
        self.assertEqual(clamp.minimum_updates_for_reference_gap(0.1210), 25)


if __name__ == "__main__":
    unittest.main()
