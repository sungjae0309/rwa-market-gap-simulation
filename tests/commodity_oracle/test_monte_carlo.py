from __future__ import annotations

import unittest
from random import Random

from rwa_market_gap.commodity_oracle.evidence import EvidenceRecord
from rwa_market_gap.commodity_oracle.monte_carlo import (
    EconomicTrial,
    run_trials,
    summarize_trials,
    triangular_from_record,
)


class EconomicTrialTests(unittest.TestCase):
    def test_net_profit_is_exact_pfc_minus_coc(self) -> None:
        trial = EconomicTrial(
            gross_pfc_usd=125.0,
            coc_usd=40.0,
            capital_at_risk_usd=200.0,
        )
        self.assertEqual(trial.net_profit_usd, 85.0)
        self.assertTrue(trial.successful)

    def test_non_executed_attempt_cannot_be_successful(self) -> None:
        trial = EconomicTrial(
            gross_pfc_usd=100.0,
            coc_usd=10.0,
            capital_at_risk_usd=0.0,
            executed=False,
        )
        self.assertFalse(trial.successful)

    def test_summary_does_not_drop_failed_attempts(self) -> None:
        outcomes = (
            EconomicTrial(100.0, 20.0, 50.0),
            EconomicTrial(0.0, 40.0, 50.0),
        )
        summary = summarize_trials(outcomes, seed=1, probability_scope="test")
        self.assertEqual(summary.expected_pfc_usd, 50.0)
        self.assertEqual(summary.expected_coc_usd, 30.0)
        self.assertEqual(summary.expected_net_profit_usd, 20.0)
        self.assertEqual(summary.success_probability, 0.5)
        self.assertEqual(summary.loss_probability, 0.5)


class SamplingTests(unittest.TestCase):
    def test_seed_makes_trial_sequence_reproducible(self) -> None:
        def factory(rng: Random) -> EconomicTrial:
            return EconomicTrial(rng.random() * 10.0, 2.0, 5.0)

        first, first_trials = run_trials(
            factory, trials=100, seed=7, probability_scope="test"
        )
        second, second_trials = run_trials(
            factory, trials=100, seed=7, probability_scope="test"
        )
        self.assertEqual(first, second)
        self.assertEqual(first_trials, second_trials)

    def test_assumption_sampler_stays_inside_declared_range(self) -> None:
        record = EvidenceRecord(
            path="test.assumption",
            value=0.5,
            unit="rate",
            definition="test input",
            grade="C",
            source="test fixture",
            as_of="2026-08-15",
            label="assumption",
            sensitivity=(0.1, 0.9),
        )
        rng = Random(3)
        samples = [triangular_from_record(record, rng) for _ in range(1_000)]
        self.assertGreaterEqual(min(samples), 0.1)
        self.assertLessEqual(max(samples), 0.9)


if __name__ == "__main__":
    unittest.main()
