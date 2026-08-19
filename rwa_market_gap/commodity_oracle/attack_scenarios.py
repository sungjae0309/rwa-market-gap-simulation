"""CoC/PfC and Monte Carlo models built on the verified commodity scenarios.

The module distinguishes an economic strategy from protocol corruption. A trader
who follows a weekend onchain signal does not pay a validator or builder attack
cost. A market deployer may additionally expose its own share of a deployment
bond to slashing. Natural-gas benchmark mismatch is deliberately not relabelled
as an attack when no adversarial control mechanism has been identified.
"""

from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Literal

from .evidence import EvidenceRecord, VerifiedInputLedger
from .monte_carlo import (
    EconomicTrial,
    MonteCarloSummary,
    run_trials,
    triangular_from_record,
)
from .scenarios import CommodityOracleScenarioEngine


WTIActor = Literal["strategic_trader", "market_deployer"]


@dataclass(frozen=True)
class WTIAttackEconomics:
    actor: WTIActor
    summary: MonteCarloSummary
    notional_usd: float
    chosen_leverage: float
    residual_gap_samples: tuple[float, ...]
    direction_accuracy: float
    break_even_residual_gap_rate: float
    bond_value_usd: float
    attacker_self_bond_fraction: float
    slashing_probability: float
    empirical_sample_count: int


@dataclass(frozen=True)
class GoldAttackEconomics:
    summary: MonteCarloSummary
    borrowed_usd: float
    collateral_oracle_value_usd: float
    observed_max_discount: float
    break_even_discount: float
    profitable_within_observed_envelope: bool


@dataclass(frozen=True)
class NaturalGasAttackAssessment:
    classified_as_attack: bool
    classification: str
    reason: str
    observed_benchmark_gap_percentage_points: float
    illustrative_hedge_shortfall_usd: float
    attack_success_probability: float | None


@dataclass(frozen=True)
class AttackEconomicsSuite:
    wti_trader: WTIAttackEconomics
    wti_deployer: WTIAttackEconomics
    natural_gas: NaturalGasAttackAssessment
    gold: GoldAttackEconomics


class CommodityAttackEconomicsEngine:
    """Scenario-specific attack economics with reproducible random sampling."""

    def __init__(self, ledger: VerifiedInputLedger | None = None) -> None:
        self.ledger = ledger or VerifiedInputLedger.load()
        self.ledger.assert_complete()
        self.base = CommodityOracleScenarioEngine(self.ledger)

    def _record(self, path: str) -> EvidenceRecord:
        return self.ledger.record(path)

    def _mode(self, path: str) -> float:
        return float(self.ledger.value(path))

    def _wti_residual_gap_samples(self) -> tuple[float, ...]:
        samples: list[float] = []
        for event in ("wti_first_weekend", "wti_second_weekend"):
            prefix = f"events.{event}"
            mark = float(self.ledger.value(f"{prefix}.observed_onchain_mark_usd"))
            reopen = float(self.ledger.value(f"{prefix}.cme_reopen_price_usd"))
            # Trading PnL is measured against the attacker's entry mark. The
            # report's 12.10 percentage-point recognition gap uses Friday close
            # as a common denominator and must not be substituted for return on
            # deployed notional (11.54% in the second event).
            samples.append(abs(reopen - mark) / mark)
        return tuple(samples)

    def wti_gap_attack(
        self,
        *,
        actor: WTIActor = "strategic_trader",
        trials: int = 20_000,
        seed: int = 20_260_815,
    ) -> WTIAttackEconomics:
        if actor not in {"strategic_trader", "market_deployer"}:
            raise ValueError("unsupported WTI actor")
        prefix = "attack_economics.wti"
        notional = self._mode(f"{prefix}.position_notional_usd")
        leverage = self._mode(f"{prefix}.chosen_leverage")
        if leverage > self.base.market("WTIOIL").max_leverage:
            raise ValueError("chosen WTI leverage exceeds the market maximum")
        horizon_hours = self._mode(f"{prefix}.horizon_hours")
        direction_accuracy = self._mode(
            "market_studies.weekend_direction_match_rate"
        )
        residual_samples = self._wti_residual_gap_samples()
        fee_record = self._record(f"{prefix}.round_trip_fee_rate")
        slippage_record = self._record(f"{prefix}.round_trip_slippage_rate")
        funding_record = self._record(f"{prefix}.funding_rate_over_horizon")
        capital_rate_record = self._record(f"{prefix}.capital_annual_rate")
        bond_value = self._mode(f"{prefix}.deployment_bond_value_usd")
        self_bond_fraction = self._mode(f"{prefix}.attacker_self_bond_fraction")
        slash_probability = self._mode(f"{prefix}.slashing_probability")
        slash_fraction = self._mode(f"{prefix}.slashing_fraction")
        margin = notional / leverage
        self_bond = (
            bond_value * self_bond_fraction
            if actor == "market_deployer"
            else 0.0
        )

        def one_trial(rng: Random) -> EconomicTrial:
            residual_gap = rng.choice(residual_samples)
            correct_direction = rng.random() < direction_accuracy
            fee_rate = triangular_from_record(fee_record, rng)
            slippage_rate = triangular_from_record(slippage_record, rng)
            funding_rate = triangular_from_record(funding_record, rng)
            annual_capital_rate = triangular_from_record(capital_rate_record, rng)
            direct_cost = notional * (fee_rate + slippage_rate + funding_rate)
            direct_cost += margin * annual_capital_rate * horizon_hours / 8_760.0
            adverse_market_loss = (
                0.0
                if correct_direction
                else min(notional * residual_gap, margin)
            )
            slashing_loss = 0.0
            if (
                actor == "market_deployer"
                and rng.random() < slash_probability
            ):
                slashing_loss = self_bond * slash_fraction
            return EconomicTrial(
                gross_pfc_usd=(
                    notional * residual_gap if correct_direction else 0.0
                ),
                coc_usd=direct_cost + adverse_market_loss + slashing_loss,
                capital_at_risk_usd=margin + self_bond,
            )

        scope = (
            "conditional on two supplied WTI stress weekends; not an "
            "unconditional annual attack probability"
        )
        summary, _ = run_trials(
            one_trial, trials=trials, seed=seed, probability_scope=scope
        )
        mode_direct_rate = (
            self._mode(f"{prefix}.round_trip_fee_rate")
            + self._mode(f"{prefix}.round_trip_slippage_rate")
            + self._mode(f"{prefix}.funding_rate_over_horizon")
            + (
                margin
                * self._mode(f"{prefix}.capital_annual_rate")
                * horizon_hours
                / 8_760.0
                / notional
            )
        )
        expected_slash_rate = (
            self_bond * slash_probability * slash_fraction / notional
        )
        return WTIAttackEconomics(
            actor=actor,
            summary=summary,
            notional_usd=notional,
            chosen_leverage=leverage,
            residual_gap_samples=residual_samples,
            direction_accuracy=direction_accuracy,
            break_even_residual_gap_rate=mode_direct_rate + expected_slash_rate,
            bond_value_usd=bond_value,
            attacker_self_bond_fraction=(
                self_bond_fraction if actor == "market_deployer" else 0.0
            ),
            slashing_probability=(
                slash_probability if actor == "market_deployer" else 0.0
            ),
            empirical_sample_count=len(residual_samples),
        )

    def _gold_profit_at_discount(
        self,
        discount: float,
        *,
        execution_rate: float,
        borrow_interest_rate: float,
        gas_usd: float,
    ) -> float:
        if not 0.0 <= discount <= 1.0:
            raise ValueError("discount must be in [0, 1]")
        ltv = float(self.ledger.value("gold_collateral.max_ltv"))
        borrowed = float(self.ledger.value("gold_collateral.debt_cap_usd"))
        collateral_face = borrowed / ltv
        acquisition = collateral_face * (1.0 - discount)
        execution = collateral_face * execution_rate
        interest = borrowed * borrow_interest_rate
        return borrowed - acquisition - execution - interest - gas_usd

    def gold_profit_at_discount(self, discount: float) -> float:
        prefix = "attack_economics.gold"
        return self._gold_profit_at_discount(
            discount,
            execution_rate=self._mode(f"{prefix}.acquisition_execution_rate"),
            borrow_interest_rate=self._mode(
                f"{prefix}.borrow_interest_rate_over_horizon"
            ),
            gas_usd=self._mode(f"{prefix}.gas_and_operations_usd"),
        )

    def gold_stale_collateral_attack(
        self,
        *,
        trials: int = 20_000,
        seed: int = 20_260_815,
    ) -> GoldAttackEconomics:
        prefix = "attack_economics.gold"
        ltv = float(self.ledger.value("gold_collateral.max_ltv"))
        borrowed = float(self.ledger.value("gold_collateral.debt_cap_usd"))
        collateral_face = borrowed / ltv
        observed_max = float(
            self.ledger.value("gold_collateral.observed_max_token_discount")
        )
        discount_record = self._record(f"{prefix}.token_discount_rate")
        execution_record = self._record(f"{prefix}.acquisition_execution_rate")
        interest_record = self._record(
            f"{prefix}.borrow_interest_rate_over_horizon"
        )
        stale_probability = self._mode(f"{prefix}.oracle_stale_probability")
        gas_usd = self._mode(f"{prefix}.gas_and_operations_usd")

        def one_trial(rng: Random) -> EconomicTrial:
            discount = triangular_from_record(discount_record, rng)
            execution_rate = triangular_from_record(execution_record, rng)
            interest_rate = triangular_from_record(interest_record, rng)
            stale_for_borrow = rng.random() < stale_probability
            acquisition_value = collateral_face * (1.0 - discount)
            execution_cost = collateral_face * execution_rate
            if not stale_for_borrow:
                return EconomicTrial(
                    gross_pfc_usd=0.0,
                    coc_usd=2.0 * execution_cost + gas_usd,
                    capital_at_risk_usd=acquisition_value + execution_cost,
                    executed=False,
                )
            return EconomicTrial(
                gross_pfc_usd=borrowed,
                coc_usd=(
                    acquisition_value
                    + execution_cost
                    + borrowed * interest_rate
                    + gas_usd
                ),
                capital_at_risk_usd=acquisition_value + execution_cost + gas_usd,
            )

        scope = (
            "conditional on the declared token-discount envelope and stale-oracle "
            "execution assumptions"
        )
        summary, _ = run_trials(
            one_trial, trials=trials, seed=seed, probability_scope=scope
        )
        execution_rate = self._mode(f"{prefix}.acquisition_execution_rate")
        interest_rate = self._mode(f"{prefix}.borrow_interest_rate_over_horizon")
        break_even_discount = (
            1.0
            + execution_rate
            - (borrowed - borrowed * interest_rate - gas_usd)
            / collateral_face
        )
        return GoldAttackEconomics(
            summary=summary,
            borrowed_usd=borrowed,
            collateral_oracle_value_usd=collateral_face,
            observed_max_discount=observed_max,
            break_even_discount=break_even_discount,
            profitable_within_observed_envelope=(
                self.gold_profit_at_discount(observed_max) > 0.0
            ),
        )

    def natural_gas_attack_assessment(self) -> NaturalGasAttackAssessment:
        result = self.base.natural_gas_benchmark_gap()
        return NaturalGasAttackAssessment(
            classified_as_attack=False,
            classification="benchmark hedge failure",
            reason=(
                "The supplied mechanism identifies a mismatched hedge, but no "
                "adversarial control action that converts the gap into protocol loss."
            ),
            observed_benchmark_gap_percentage_points=(
                result.benchmark_gap_percentage_points
            ),
            illustrative_hedge_shortfall_usd=result.proxy_hedge_shortfall_usd,
            attack_success_probability=None,
        )

    def run_all(
        self, *, trials: int = 20_000, seed: int = 20_260_815
    ) -> AttackEconomicsSuite:
        return AttackEconomicsSuite(
            wti_trader=self.wti_gap_attack(
                actor="strategic_trader", trials=trials, seed=seed
            ),
            wti_deployer=self.wti_gap_attack(
                actor="market_deployer", trials=trials, seed=seed
            ),
            natural_gas=self.natural_gas_attack_assessment(),
            gold=self.gold_stale_collateral_attack(trials=trials, seed=seed),
        )
