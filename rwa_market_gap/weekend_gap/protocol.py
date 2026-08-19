"""Protocol-aware Weekend Gap model kept separate from the draft baseline.

The ``weekend_gap.baseline`` module faithfully reproduces the research
draft's closed-form equations.  This module adds the checks that are needed
before discussing a specific lending protocol:

* closed-market oracle eligibility, freshness, and price bands;
* reserve supply/borrow caps, available liquidity, and borrow factors;
* a utilization-based interest-rate curve;
* iterative close-factor liquidations and a time-varying liquidation bonus;
* explicit AMM reserves or a captured aggregator quote; and
* full gap-sample evaluation instead of a two-state success/failure shortcut.

No default in this file is presented as a live Kamino or xStocks parameter.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import ceil, exp, isfinite
from statistics import fmean
from typing import Iterable

from .protocol_config import (
    DEFAULT_PROTOCOL_AWARE_WEEKEND_GAP_CONFIG,
    ProtocolAwareWeekendGapConfig,
)


SECONDS_PER_YEAR = 365.0 * 24.0 * 60.0 * 60.0
EPSILON = 1e-9


@dataclass(frozen=True)
class OriginationDecision:
    """Whether the requested weekend loan can be opened and how it is sized."""

    allowed: bool
    blocking_reasons: tuple[str, ...]
    oracle_collateral_value_usd: float
    remaining_collateral_cap_usd: float
    ltv_borrow_capacity_usd: float
    remaining_debt_borrow_cap_usd: float
    available_debt_liquidity_usd: float
    borrowed_principal_usd: float
    utilization_before: float
    utilization_after: float
    annual_borrow_rate: float
    debt_at_market_reopen_usd: float
    accrued_interest_usd: float
    liquidation_start_gap: float
    principal_insolvency_gap: float
    protocol_inputs_verified: bool


@dataclass(frozen=True)
class LiquidationRound:
    """One executed partial-liquidation round."""

    elapsed_seconds: float
    bonus_rate: float
    debt_repaid_usd: float
    collateral_seized_usd: float
    liquidator_sale_proceeds_usd: float
    liquidator_profit_usd: float
    debt_after_usd: float
    collateral_after_usd: float


@dataclass(frozen=True)
class LiquidationPath:
    """Iterative liquidation outcome at the post-gap true price."""

    initially_liquidatable: bool
    attempts: int
    executed_rounds: tuple[LiquidationRound, ...]
    first_execution_seconds: float | None
    total_debt_repaid_usd: float
    total_collateral_seized_usd: float
    total_liquidator_profit_usd: float
    remaining_debt_usd: float
    remaining_collateral_usd: float
    remains_unhealthy: bool
    projected_collateral_recovery_usd: float
    projected_principal_shortfall_usd: float


@dataclass(frozen=True)
class ProtocolAwareGapOutcome:
    """Attacker, liquidator, and protocol result for one signed weekend gap."""

    monday_gap: float
    market_reopen_price_usd: float
    origination: OriginationDecision
    amm_sale_proceeds_usd: float
    borrow_minus_sale_usd: float
    post_gap_hold_value_usd: float
    liquidation: LiquidationPath
    attacker_repay_wealth_usd: float
    attacker_abandon_wealth_usd: float
    strategically_defaults: bool
    attacker_terminal_wealth_usd: float
    direct_attacker_cost_usd: float
    attacker_net_profit_vs_hold_usd: float
    protocol_bad_debt_usd: float
    empirically_calibrated: bool

    @property
    def profitable(self) -> bool:
        return self.attacker_net_profit_vs_hold_usd > 0.0


@dataclass(frozen=True)
class GapSampleSummary:
    """Expected result obtained from every observation in a supplied dataset."""

    sample_source: str
    sample_size: int
    mean_gap: float
    minimum_gap: float
    maximum_gap: float
    origination_allowed: bool
    profitable_sample_rate: float
    strategic_default_rate: float
    expected_attacker_net_profit_usd: float
    expected_protocol_bad_debt_usd: float
    worst_attacker_net_profit_usd: float
    best_attacker_net_profit_usd: float
    empirically_calibrated: bool
    outcomes: tuple[ProtocolAwareGapOutcome, ...]


class ProtocolAwareWeekendGapEngine:
    """Evaluate the weekend hypothesis subject to explicit protocol controls."""

    def __init__(
        self,
        config: ProtocolAwareWeekendGapConfig | None = None,
    ) -> None:
        self.config = config or DEFAULT_PROTOCOL_AWARE_WEEKEND_GAP_CONFIG

    def annual_borrow_rate(self, utilization: float) -> float:
        """Return the piecewise-linear reserve rate at one utilization level."""

        if not 0.0 <= utilization <= 1.0:
            raise ValueError("utilization must be in [0, 1]")
        curve = self.config.interest_curve
        if utilization <= curve.kink_utilization:
            slope_fraction = utilization / curve.kink_utilization
            reserve_rate = curve.base_rate + slope_fraction * (
                curve.rate_at_kink - curve.base_rate
            )
        else:
            slope_fraction = (
                (utilization - curve.kink_utilization)
                / (1.0 - curve.kink_utilization)
            )
            reserve_rate = curve.rate_at_kink + slope_fraction * (
                curve.maximum_rate - curve.rate_at_kink
            )
        return reserve_rate + curve.position_risk_premium

    def origination_decision(self) -> OriginationDecision:
        """Apply oracle guards, caps, liquidity, LTV, and borrow-factor rules."""

        cfg = self.config
        oracle = cfg.oracle
        reserve = cfg.reserve
        reasons: list[str] = []

        if not reserve.new_loans_allowed:
            reasons.append("reserve blocks new loans")

        if oracle.market_status in {"halted", "unknown"}:
            reasons.append(f"market status is {oracle.market_status}")
        elif oracle.market_status == "closed":
            if not oracle.allow_new_loans_when_market_closed:
                reasons.append("closed-market new loans are disabled")
            if (
                oracle.deviation_from_last_close
                > oracle.closed_market_price_band_rate + EPSILON
            ):
                reasons.append("oracle price is outside the closed-market price band")
            if (
                not oracle.closed_market_staleness_exemption
                and oracle.feed_age_seconds
                > oracle.max_feed_age_for_new_loan_seconds
            ):
                reasons.append("closed-market oracle price is too old for a new loan")
        elif (
            oracle.feed_age_seconds > oracle.max_feed_age_for_new_loan_seconds
        ):
            reasons.append("oracle price is too old for a new loan")

        collateral_value = (
            reserve.collateral_amount_units * oracle.oracle_price_usd
        )
        remaining_collateral_cap = max(
            0.0,
            reserve.collateral_supply_cap_usd
            - reserve.collateral_supplied_before_attack_usd,
        )
        if collateral_value > remaining_collateral_cap + EPSILON:
            reasons.append("requested collateral exceeds the remaining supply cap")

        ltv_capacity = (
            collateral_value * reserve.max_ltv / reserve.debt_borrow_factor
        )
        remaining_debt_cap = max(
            0.0,
            reserve.debt_borrow_cap_usd
            - reserve.debt_reserve_current_borrowed_usd,
        )
        available_liquidity = max(
            0.0,
            reserve.debt_reserve_total_supply_usd
            - reserve.debt_reserve_current_borrowed_usd,
        )
        maximum_borrow = min(ltv_capacity, remaining_debt_cap, available_liquidity)
        if maximum_borrow <= EPSILON:
            reasons.append("no debt capacity or liquid debt reserve is available")

        total_supply = reserve.debt_reserve_total_supply_usd
        utilization_before = (
            reserve.debt_reserve_current_borrowed_usd / total_supply
            if total_supply > 0.0
            else 1.0
        )
        allowed = not reasons
        borrowed = maximum_borrow if allowed else 0.0
        utilization_after = (
            min(
                1.0,
                (reserve.debt_reserve_current_borrowed_usd + borrowed)
                / total_supply,
            )
            if total_supply > 0.0
            else 1.0
        )
        annual_rate = self.annual_borrow_rate(utilization_after) if allowed else 0.0
        elapsed_seconds = cfg.attack.closure_hours * 60.0 * 60.0
        debt_at_reopen = (
            borrowed * exp(annual_rate * elapsed_seconds / SECONDS_PER_YEAR)
            if allowed
            else 0.0
        )
        accrued_interest = debt_at_reopen - borrowed

        close_value = (
            reserve.collateral_amount_units * oracle.last_close_price_usd
        )
        if allowed and close_value > 0.0:
            liquidation_start_gap = 1.0 - (
                debt_at_reopen
                * reserve.debt_borrow_factor
                / (close_value * reserve.liquidation_ltv)
            )
            principal_insolvency_gap = 1.0 - debt_at_reopen / close_value
        else:
            liquidation_start_gap = float("inf")
            principal_insolvency_gap = float("inf")

        return OriginationDecision(
            allowed=allowed,
            blocking_reasons=tuple(reasons),
            oracle_collateral_value_usd=collateral_value,
            remaining_collateral_cap_usd=remaining_collateral_cap,
            ltv_borrow_capacity_usd=ltv_capacity,
            remaining_debt_borrow_cap_usd=remaining_debt_cap,
            available_debt_liquidity_usd=available_liquidity,
            borrowed_principal_usd=borrowed,
            utilization_before=utilization_before,
            utilization_after=utilization_after,
            annual_borrow_rate=annual_rate,
            debt_at_market_reopen_usd=debt_at_reopen,
            accrued_interest_usd=accrued_interest,
            liquidation_start_gap=liquidation_start_gap,
            principal_insolvency_gap=principal_insolvency_gap,
            protocol_inputs_verified=cfg.evidence.protocol_inputs_verified,
        )

    def amm_sale_proceeds_usd(self) -> float:
        """Return a captured full-position quote or an explicit CPMM output."""

        cfg = self.config
        liquidity = cfg.liquidity
        if liquidity.aggregator_quote_for_full_position_usd is not None:
            return liquidity.aggregator_quote_for_full_position_usd
        effective_input = (
            cfg.reserve.collateral_amount_units * (1.0 - liquidity.swap_fee_rate)
        )
        return (
            liquidity.stable_reserve_usd
            * effective_input
            / (liquidity.asset_reserve_units + effective_input)
        )

    def liquidation_bonus(self, elapsed_seconds: float) -> float:
        """Linearly ramp the bonus from its minimum to maximum."""

        mechanism = self.config.liquidation
        if mechanism.bonus_ramp_hours == 0.0:
            return mechanism.maximum_bonus
        ramp_seconds = mechanism.bonus_ramp_hours * 60.0 * 60.0
        progress = min(max(elapsed_seconds / ramp_seconds, 0.0), 1.0)
        return mechanism.minimum_bonus + progress * (
            mechanism.maximum_bonus - mechanism.minimum_bonus
        )

    def _is_unhealthy(self, debt_usd: float, collateral_usd: float) -> bool:
        if debt_usd <= EPSILON:
            return False
        if collateral_usd <= EPSILON:
            return True
        reserve = self.config.reserve
        current_ltv = debt_usd * reserve.debt_borrow_factor / collateral_usd
        return current_ltv > reserve.liquidation_ltv + EPSILON

    def _liquidation_path(
        self,
        *,
        debt_usd: float,
        collateral_usd: float,
    ) -> LiquidationPath:
        mechanism = self.config.liquidation
        initially_liquidatable = self._is_unhealthy(debt_usd, collateral_usd)
        remaining_debt = debt_usd
        remaining_collateral = collateral_usd
        attempts = 0
        executed: list[LiquidationRound] = []
        first_execution: float | None = None
        elapsed = 0.0
        maximum_seconds = mechanism.maximum_simulation_hours * 60.0 * 60.0
        maximum_attempts = max(
            1,
            ceil(maximum_seconds / mechanism.round_interval_seconds) + 1,
        )

        while (
            initially_liquidatable
            and self._is_unhealthy(remaining_debt, remaining_collateral)
            and remaining_debt > EPSILON
            and remaining_collateral > EPSILON
            and attempts < maximum_attempts
            and elapsed <= maximum_seconds + EPSILON
        ):
            attempts += 1
            bonus = self.liquidation_bonus(elapsed)
            target_repayment = min(
                remaining_debt * mechanism.close_factor,
                mechanism.max_debt_repaid_per_round_usd,
                remaining_collateral / (1.0 + bonus),
            )
            collateral_seized = target_repayment * (1.0 + bonus)
            sale_proceeds = collateral_seized * (
                1.0 - mechanism.collateral_sale_slippage_rate
            )
            liquidator_profit = (
                sale_proceeds
                - target_repayment
                - mechanism.execution_cost_per_round_usd
            )

            if (
                target_repayment > EPSILON
                and liquidator_profit + EPSILON
                >= mechanism.minimum_liquidator_profit_usd
            ):
                remaining_debt = max(0.0, remaining_debt - target_repayment)
                remaining_collateral = max(
                    0.0, remaining_collateral - collateral_seized
                )
                if first_execution is None:
                    first_execution = elapsed
                executed.append(
                    LiquidationRound(
                        elapsed_seconds=elapsed,
                        bonus_rate=bonus,
                        debt_repaid_usd=target_repayment,
                        collateral_seized_usd=collateral_seized,
                        liquidator_sale_proceeds_usd=sale_proceeds,
                        liquidator_profit_usd=liquidator_profit,
                        debt_after_usd=remaining_debt,
                        collateral_after_usd=remaining_collateral,
                    )
                )
            elif bonus >= mechanism.maximum_bonus - EPSILON:
                break

            elapsed += mechanism.round_interval_seconds

        projected_recovery = remaining_collateral * (
            1.0 - mechanism.collateral_sale_slippage_rate
        )
        projected_shortfall = max(0.0, remaining_debt - projected_recovery)
        return LiquidationPath(
            initially_liquidatable=initially_liquidatable,
            attempts=attempts,
            executed_rounds=tuple(executed),
            first_execution_seconds=first_execution,
            total_debt_repaid_usd=sum(r.debt_repaid_usd for r in executed),
            total_collateral_seized_usd=sum(
                r.collateral_seized_usd for r in executed
            ),
            total_liquidator_profit_usd=sum(
                r.liquidator_profit_usd for r in executed
            ),
            remaining_debt_usd=remaining_debt,
            remaining_collateral_usd=remaining_collateral,
            remains_unhealthy=self._is_unhealthy(
                remaining_debt, remaining_collateral
            ),
            projected_collateral_recovery_usd=projected_recovery,
            projected_principal_shortfall_usd=projected_shortfall,
        )

    def realized(self, monday_gap: float) -> ProtocolAwareGapOutcome:
        """Evaluate one gap; positive is a decline and negative is a rise."""

        if not isfinite(monday_gap) or monday_gap > 1.0:
            raise ValueError("monday_gap must be finite and no greater than 1")

        cfg = self.config
        origination = self.origination_decision()
        reopen_price = cfg.oracle.last_close_price_usd * (1.0 - monday_gap)
        hold_value = cfg.reserve.collateral_amount_units * reopen_price
        amm_proceeds = self.amm_sale_proceeds_usd()

        if not origination.allowed:
            empty_liquidation = self._liquidation_path(
                debt_usd=0.0,
                collateral_usd=hold_value,
            )
            return ProtocolAwareGapOutcome(
                monday_gap=monday_gap,
                market_reopen_price_usd=reopen_price,
                origination=origination,
                amm_sale_proceeds_usd=amm_proceeds,
                borrow_minus_sale_usd=-amm_proceeds,
                post_gap_hold_value_usd=hold_value,
                liquidation=empty_liquidation,
                attacker_repay_wealth_usd=hold_value,
                attacker_abandon_wealth_usd=hold_value,
                strategically_defaults=False,
                attacker_terminal_wealth_usd=hold_value,
                direct_attacker_cost_usd=0.0,
                attacker_net_profit_vs_hold_usd=0.0,
                protocol_bad_debt_usd=0.0,
                empirically_calibrated=cfg.evidence.fully_verified,
            )

        principal = origination.borrowed_principal_usd
        debt = origination.debt_at_market_reopen_usd
        liquidation = self._liquidation_path(
            debt_usd=debt,
            collateral_usd=hold_value,
        )
        retained_cash = principal * cfg.attack.borrowed_cash_exit_recovery_rate
        repay_wealth = (
            retained_cash
            + liquidation.remaining_collateral_usd
            - liquidation.remaining_debt_usd
        )
        abandon_wealth = retained_cash
        strategically_defaults = (
            cfg.attack.non_recourse_default
            and abandon_wealth > repay_wealth + EPSILON
        )
        terminal_wealth = abandon_wealth if strategically_defaults else repay_wealth

        financing_cost = (
            origination.oracle_collateral_value_usd
            * cfg.attack.annual_collateral_financing_rate
            * cfg.attack.closure_hours
            / (365.0 * 24.0)
        )
        direct_cost = (
            cfg.attack.origination_transaction_cost_usd + financing_cost
        )
        if not strategically_defaults:
            direct_cost += cfg.attack.repayment_transaction_cost_usd

        protocol_bad_debt = (
            liquidation.projected_principal_shortfall_usd
            if strategically_defaults
            else 0.0
        )
        return ProtocolAwareGapOutcome(
            monday_gap=monday_gap,
            market_reopen_price_usd=reopen_price,
            origination=origination,
            amm_sale_proceeds_usd=amm_proceeds,
            borrow_minus_sale_usd=principal - amm_proceeds,
            post_gap_hold_value_usd=hold_value,
            liquidation=liquidation,
            attacker_repay_wealth_usd=repay_wealth,
            attacker_abandon_wealth_usd=abandon_wealth,
            strategically_defaults=strategically_defaults,
            attacker_terminal_wealth_usd=terminal_wealth,
            direct_attacker_cost_usd=direct_cost,
            attacker_net_profit_vs_hold_usd=(
                terminal_wealth - hold_value - direct_cost
            ),
            protocol_bad_debt_usd=protocol_bad_debt,
            empirically_calibrated=cfg.evidence.fully_verified,
        )

    def evaluate_gap_samples(
        self,
        gaps: Iterable[float],
        *,
        sample_source: str,
    ) -> GapSampleSummary:
        """Evaluate the complete observed/synthetic gap distribution."""

        gap_values = tuple(gaps)
        if not gap_values:
            raise ValueError("at least one gap observation is required")
        if not sample_source.strip():
            raise ValueError("sample_source must not be blank")
        outcomes = tuple(self.realized(gap) for gap in gap_values)
        profits = tuple(o.attacker_net_profit_vs_hold_usd for o in outcomes)
        bad_debts = tuple(o.protocol_bad_debt_usd for o in outcomes)
        return GapSampleSummary(
            sample_source=sample_source,
            sample_size=len(outcomes),
            mean_gap=fmean(gap_values),
            minimum_gap=min(gap_values),
            maximum_gap=max(gap_values),
            origination_allowed=outcomes[0].origination.allowed,
            profitable_sample_rate=fmean(float(o.profitable) for o in outcomes),
            strategic_default_rate=fmean(
                float(o.strategically_defaults) for o in outcomes
            ),
            expected_attacker_net_profit_usd=fmean(profits),
            expected_protocol_bad_debt_usd=fmean(bad_debts),
            worst_attacker_net_profit_usd=min(profits),
            best_attacker_net_profit_usd=max(profits),
            empirically_calibrated=self.config.evidence.fully_verified,
            outcomes=outcomes,
        )


def _money(value: float) -> str:
    return f"${value:,.2f}"


def main() -> None:
    """Show the guarded default and a clearly labelled illustrative run."""

    guarded = ProtocolAwareWeekendGapEngine()
    decision = guarded.origination_decision()
    print("Protocol-aware Weekend Gap model")
    print(f"default origination allowed: {decision.allowed}")
    print(f"blocking reasons: {', '.join(decision.blocking_reasons)}")

    illustrative_config = replace(
        guarded.config,
        oracle=replace(
            guarded.config.oracle,
            allow_new_loans_when_market_closed=True,
            closed_market_staleness_exemption=True,
        ),
    )
    illustrative = ProtocolAwareWeekendGapEngine(illustrative_config)
    print("\nILLUSTRATIVE ONLY - not a live protocol snapshot")
    for gap in (-0.05, 0.10, 0.20, 0.30, 0.35):
        outcome = illustrative.realized(gap)
        print(
            f"gap={gap:>6.1%}, default={outcome.strategically_defaults}, "
            f"net={_money(outcome.attacker_net_profit_vs_hold_usd)}, "
            f"bad debt={_money(outcome.protocol_bad_debt_usd)}"
        )


if __name__ == "__main__":
    main()
