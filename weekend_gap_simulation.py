"""Deterministic baseline for the tokenized-equity weekend-gap scenario.

The model reproduces illustrative research equations. It does not assume that
weekend borrowing is live in any specific protocol. All values remain scenario
inputs until verified from protocol configuration and market data.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from weekend_gap_config import WeekendGapConfig


@dataclass(frozen=True)
class WeekendGapOutcome:
    """Realized result for one Monday price gap."""

    monday_gap: float
    borrowing_enabled: bool
    borrowed_usd: float
    amm_sale_proceeds_usd: float
    borrow_advantage_usd: float
    minimum_collateral_for_borrow_advantage_usd: float
    attack_profit_threshold: float
    liquidation_incentive_shortfall_threshold: float
    post_gap_collateral_usd: float
    liquidatable: bool
    liquidation_bonus_fully_covered: bool
    attacker_terminal_wealth_usd: float
    hold_terminal_wealth_usd: float
    gross_incremental_profit_usd: float
    interest_cost_usd: float
    transaction_cost_usd: float
    net_incremental_profit_usd: float
    principal_bad_debt_usd: float
    liquidation_incentive_shortfall_usd: float

    @property
    def prefers_borrow_to_amm_sale(self) -> bool:
        return self.borrow_advantage_usd > 0.0

    @property
    def strategically_defaults(self) -> bool:
        return self.borrowing_enabled and self.principal_bad_debt_usd > 0.0


@dataclass(frozen=True)
class ExpectedWeekendGapOutcome:
    """Ex-ante payoff with a success belief and a failed-signal penalty."""

    success_probability: float
    expected_success_gap: float
    excess_gap_above_attack_threshold: float
    conditional_success_profit_usd: float
    failure_liquidation_penalty_usd: float
    fixed_execution_cost_usd: float
    expected_profit_usd: float
    expected_cost_usd: float
    expected_net_profit_usd: float
    simplified_break_even_probability: float
    exact_break_even_probability: float

    @property
    def expected_viable(self) -> bool:
        return self.expected_net_profit_usd > 0.0


@dataclass(frozen=True)
class LiquidatorParticipation:
    """Whether a fixed liquidation bonus covers a chosen gap-risk quantile."""

    gap_quantile: float
    funding_cost_rate: float
    execution_cost_rate: float
    required_bonus_rate: float
    configured_bonus_rate: float
    participates: bool


class WeekendGapEngine:
    """Compute realized, expected, and sensitivity results for the gap model."""

    def __init__(self, config: WeekendGapConfig | None = None) -> None:
        self.config = config or WeekendGapConfig()

    @property
    def attack_profit_threshold(self) -> float:
        """Gap ``g* = 1 - LTV`` where debt first exceeds collateral."""

        return 1.0 - self.config.ltv

    @property
    def liquidation_incentive_shortfall_threshold(self) -> float:
        """Gap where collateral no longer covers debt plus liquidator bonus."""

        return 1.0 - self.config.ltv * (1.0 + self.config.liquidation_bonus)

    @property
    def borrowed_usd(self) -> float:
        if not self.config.new_borrowing_enabled:
            return 0.0
        return self.config.collateral_value_usd * self.config.ltv

    @property
    def interest_cost_usd(self) -> float:
        return (
            self.borrowed_usd
            * self.config.annual_borrow_rate
            * self.config.closure_hours
            / (365.0 * 24.0)
        )

    @property
    def amm_sale_proceeds_usd(self) -> float:
        """CPMM sale proceeds ``C0 * Y / (Y + C0)`` from the draft."""

        collateral = self.config.collateral_value_usd
        depth = self.config.onchain_pool_depth_usd
        if collateral == 0.0 or depth == 0.0:
            return 0.0
        return collateral * depth / (depth + collateral)

    @property
    def minimum_collateral_for_borrow_advantage_usd(self) -> float:
        """Position threshold ``Y * (1-LTV) / LTV`` from the draft."""

        if self.config.ltv == 0.0:
            return float("inf")
        return (
            self.config.onchain_pool_depth_usd
            * (1.0 - self.config.ltv)
            / self.config.ltv
        )

    def realized(self, monday_gap: float) -> WeekendGapOutcome:
        """Evaluate the borrow/repay/liquidate/default path for one gap."""

        self._validate_probability("monday_gap", monday_gap)
        cfg = self.config
        collateral = cfg.collateral_value_usd
        post_gap_collateral = collateral * (1.0 - monday_gap)
        borrowed = self.borrowed_usd
        interest = self.interest_cost_usd
        transaction_cost = cfg.transaction_cost_usd if borrowed > 0.0 else 0.0

        if borrowed == 0.0:
            return WeekendGapOutcome(
                monday_gap=monday_gap,
                borrowing_enabled=False,
                borrowed_usd=0.0,
                amm_sale_proceeds_usd=self.amm_sale_proceeds_usd,
                borrow_advantage_usd=-self.amm_sale_proceeds_usd,
                minimum_collateral_for_borrow_advantage_usd=(
                    self.minimum_collateral_for_borrow_advantage_usd
                ),
                attack_profit_threshold=self.attack_profit_threshold,
                liquidation_incentive_shortfall_threshold=(
                    self.liquidation_incentive_shortfall_threshold
                ),
                post_gap_collateral_usd=post_gap_collateral,
                liquidatable=False,
                liquidation_bonus_fully_covered=False,
                attacker_terminal_wealth_usd=post_gap_collateral,
                hold_terminal_wealth_usd=post_gap_collateral,
                gross_incremental_profit_usd=0.0,
                interest_cost_usd=0.0,
                transaction_cost_usd=0.0,
                net_incremental_profit_usd=0.0,
                principal_bad_debt_usd=0.0,
                liquidation_incentive_shortfall_usd=0.0,
            )

        liquidatable = (
            post_gap_collateral * cfg.liquidation_threshold < borrowed
        )
        collateral_needed_with_bonus = borrowed * (1.0 + cfg.liquidation_bonus)
        bonus_fully_covered = post_gap_collateral >= collateral_needed_with_bonus

        if not liquidatable:
            terminal_wealth = post_gap_collateral
        elif bonus_fully_covered:
            terminal_wealth = (
                borrowed + post_gap_collateral - collateral_needed_with_bonus
            )
        else:
            # All collateral is consumed. The borrower retains the borrowed cash.
            terminal_wealth = borrowed

        gross_incremental_profit = terminal_wealth - post_gap_collateral
        principal_bad_debt = max(0.0, borrowed - post_gap_collateral)
        liquidation_shortfall = max(
            0.0, collateral_needed_with_bonus - post_gap_collateral
        )

        return WeekendGapOutcome(
            monday_gap=monday_gap,
            borrowing_enabled=True,
            borrowed_usd=borrowed,
            amm_sale_proceeds_usd=self.amm_sale_proceeds_usd,
            borrow_advantage_usd=borrowed - self.amm_sale_proceeds_usd,
            minimum_collateral_for_borrow_advantage_usd=(
                self.minimum_collateral_for_borrow_advantage_usd
            ),
            attack_profit_threshold=self.attack_profit_threshold,
            liquidation_incentive_shortfall_threshold=(
                self.liquidation_incentive_shortfall_threshold
            ),
            post_gap_collateral_usd=post_gap_collateral,
            liquidatable=liquidatable,
            liquidation_bonus_fully_covered=bonus_fully_covered,
            attacker_terminal_wealth_usd=terminal_wealth,
            hold_terminal_wealth_usd=post_gap_collateral,
            gross_incremental_profit_usd=gross_incremental_profit,
            interest_cost_usd=interest,
            transaction_cost_usd=transaction_cost,
            net_incremental_profit_usd=(
                gross_incremental_profit - interest - transaction_cost
            ),
            principal_bad_debt_usd=principal_bad_debt,
            liquidation_incentive_shortfall_usd=liquidation_shortfall,
        )

    def expected(
        self,
        *,
        success_probability: float,
        expected_success_gap: float,
    ) -> ExpectedWeekendGapOutcome:
        """Apply the draft's probability-weighted strategic-default equation.

        ``p * C0 * (E[g|success] - g*)`` is the expected upside.
        ``(1-p) * C0 * LTV * b`` is the failed-signal liquidation penalty.
        Interest and transaction costs are paid independently of the signal.
        """

        self._validate_probability("success_probability", success_probability)
        self._validate_probability("expected_success_gap", expected_success_gap)

        cfg = self.config
        collateral = cfg.collateral_value_usd
        excess_gap = max(0.0, expected_success_gap - self.attack_profit_threshold)
        success_profit = collateral * excess_gap
        failure_penalty = collateral * cfg.ltv * cfg.liquidation_bonus
        fixed_cost = self.interest_cost_usd + (
            cfg.transaction_cost_usd if self.borrowed_usd > 0.0 else 0.0
        )

        if not cfg.new_borrowing_enabled:
            success_profit = 0.0
            failure_penalty = 0.0
            fixed_cost = 0.0

        expected_profit = success_probability * success_profit
        expected_cost = (1.0 - success_probability) * failure_penalty + fixed_cost

        denominator = success_profit + failure_penalty
        if denominator == 0.0:
            simplified_break_even = float("inf")
            exact_break_even = float("inf")
        else:
            simplified_break_even = failure_penalty / denominator
            exact_break_even = (failure_penalty + fixed_cost) / denominator

        return ExpectedWeekendGapOutcome(
            success_probability=success_probability,
            expected_success_gap=expected_success_gap,
            excess_gap_above_attack_threshold=excess_gap,
            conditional_success_profit_usd=success_profit,
            failure_liquidation_penalty_usd=failure_penalty,
            fixed_execution_cost_usd=fixed_cost,
            expected_profit_usd=expected_profit,
            expected_cost_usd=expected_cost,
            expected_net_profit_usd=expected_profit - expected_cost,
            simplified_break_even_probability=simplified_break_even,
            exact_break_even_probability=exact_break_even,
        )

    def liquidator_participation(
        self,
        *,
        gap_quantile: float,
        execution_cost_usd: float = 0.0,
    ) -> LiquidatorParticipation:
        """Evaluate ``b >= q_alpha(gap) + funding + execution / C``."""

        self._validate_probability("gap_quantile", gap_quantile)
        if execution_cost_usd < 0.0:
            raise ValueError("execution_cost_usd must be non-negative")

        cfg = self.config
        funding_cost_rate = (
            cfg.annual_borrow_rate * cfg.closure_hours / (365.0 * 24.0)
        )
        execution_cost_rate = (
            execution_cost_usd / cfg.collateral_value_usd
            if cfg.collateral_value_usd > 0.0
            else float("inf")
        )
        required_bonus = gap_quantile + funding_cost_rate + execution_cost_rate
        return LiquidatorParticipation(
            gap_quantile=gap_quantile,
            funding_cost_rate=funding_cost_rate,
            execution_cost_rate=execution_cost_rate,
            required_bonus_rate=required_bonus,
            configured_bonus_rate=cfg.liquidation_bonus,
            participates=cfg.liquidation_bonus >= required_bonus,
        )

    def sweep_gaps(self, gaps: Iterable[float]) -> tuple[WeekendGapOutcome, ...]:
        return tuple(self.realized(gap) for gap in gaps)

    def sweep_ltv(
        self, ltvs: Iterable[float], *, monday_gap: float
    ) -> tuple[WeekendGapOutcome, ...]:
        return tuple(
            WeekendGapEngine(replace(self.config, ltv=ltv)).realized(monday_gap)
            for ltv in ltvs
        )

    @staticmethod
    def _validate_probability(name: str, value: float) -> None:
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be in [0, 1], got {value}")


def _money(value: float) -> str:
    return f"${value:,.2f}"


def main() -> None:
    """Print the draft's reference path and a compact LTV sensitivity table."""

    engine = WeekendGapEngine()
    cfg = engine.config
    print("Weekend gap deterministic baseline")
    print(
        f"C0={_money(cfg.collateral_value_usd)}, LTV={cfg.ltv:.0%}, "
        f"bonus={cfg.liquidation_bonus:.0%}, closure={cfg.closure_hours:.0f}h"
    )
    print(
        f"attack threshold={engine.attack_profit_threshold:.1%}, "
        "liquidation-incentive shortfall threshold="
        f"{engine.liquidation_incentive_shortfall_threshold:.1%}"
    )
    print(
        f"AMM proceeds={_money(engine.amm_sale_proceeds_usd)}, "
        f"borrowed={_money(engine.borrowed_usd)}, "
        "minimum position for borrow advantage="
        f"{_money(engine.minimum_collateral_for_borrow_advantage_usd)}"
    )
    borrow_advantage = engine.borrowed_usd - engine.amm_sale_proceeds_usd
    print(
        f"borrow preferred over CPMM sale={borrow_advantage > 0.0}, "
        f"borrow advantage={_money(borrow_advantage)}"
    )

    print("\nGap path")
    print("gap | liquidatable | gross incremental | principal bad debt | net")
    for outcome in engine.sweep_gaps((0.10, 0.20, 0.30, 0.35)):
        print(
            f"{outcome.monday_gap:>4.0%} | "
            f"{str(outcome.liquidatable):>12} | "
            f"{_money(outcome.gross_incremental_profit_usd):>17} | "
            f"{_money(outcome.principal_bad_debt_usd):>18} | "
            f"{_money(outcome.net_incremental_profit_usd):>12}"
        )

    expected = engine.expected(
        success_probability=0.26,
        expected_success_gap=0.40,
    )
    print("\nExpected-value example (p=26%, E[g|success]=40%)")
    print(f"conditional success profit={_money(expected.conditional_success_profit_usd)}")
    print(f"failure penalty={_money(expected.failure_liquidation_penalty_usd)}")
    print(f"fixed cost={_money(expected.fixed_execution_cost_usd)}")
    print(f"expected net={_money(expected.expected_net_profit_usd)}")
    print(
        "break-even p: simplified="
        f"{expected.simplified_break_even_probability:.2%}, "
        f"including fixed costs={expected.exact_break_even_probability:.2%}"
    )

    print("\nLTV sensitivity (same bonus and pool depth)")
    print("LTV | attack threshold | incentive shortfall | minimum C0 for borrow")
    for ltv in (0.60, 0.70, 0.75, 0.80, 0.85, 0.90):
        attack_threshold = 1.0 - ltv
        shortfall_threshold = 1.0 - ltv * (1.0 + cfg.liquidation_bonus)
        minimum_position = cfg.onchain_pool_depth_usd * (1.0 - ltv) / ltv
        print(
            f"{ltv:>3.0%} | {attack_threshold:>16.1%} | "
            f"{shortfall_threshold:>19.1%} | {_money(minimum_position):>21}"
        )


if __name__ == "__main__":
    main()
