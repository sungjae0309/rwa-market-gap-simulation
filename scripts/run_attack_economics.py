"""Run the assumption-conditioned commodity attack-economics models."""

from __future__ import annotations

import argparse

from rwa_market_gap.commodity_oracle.attack_scenarios import (
    CommodityAttackEconomicsEngine,
)


def usd(value: float) -> str:
    return f"${value:,.2f}"


def print_summary(label: str, result: object) -> None:
    summary = result.summary
    print(label)
    print(
        f"E[PfC]={usd(summary.expected_pfc_usd)}, "
        f"E[CoC]={usd(summary.expected_coc_usd)}, "
        f"E[net]={usd(summary.expected_net_profit_usd)}"
    )
    print(
        f"success={summary.success_probability:.2%}, "
        f"loss={summary.loss_probability:.2%}, "
        f"capital at risk={usd(summary.expected_capital_at_risk_usd)}"
    )
    print(
        f"net p05/median/p95={usd(summary.net_profit_p05_usd)} / "
        f"{usd(summary.net_profit_median_usd)} / "
        f"{usd(summary.net_profit_p95_usd)}, "
        f"CVaR95={usd(summary.conditional_value_at_risk_95_usd)}"
    )
    print(f"scope: {summary.probability_scope}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=20_260_815)
    args = parser.parse_args()
    engine = CommodityAttackEconomicsEngine()
    suite = engine.run_all(trials=args.trials, seed=args.seed)

    print_summary("WTI strategic trader", suite.wti_trader)
    print(
        "WTI trader break-even residual gap="
        f"{suite.wti_trader.break_even_residual_gap_rate:.2%}"
    )
    print()

    print_summary("WTI market deployer", suite.wti_deployer)
    print(
        "WTI deployer expected-cost break-even residual gap="
        f"{suite.wti_deployer.break_even_residual_gap_rate:.2%}"
    )
    print()

    gas = suite.natural_gas
    print("Natural-gas classification")
    print(f"attack={gas.classified_as_attack}, classification={gas.classification}")
    print(
        f"observed benchmark gap={gas.observed_benchmark_gap_percentage_points:.1%}p, "
        f"illustrative hedge shortfall={usd(gas.illustrative_hedge_shortfall_usd)}"
    )
    print(f"reason: {gas.reason}")
    print()

    print_summary("Tokenized-gold stale-collateral attempt", suite.gold)
    print(
        f"observed max discount={suite.gold.observed_max_discount:.2%}, "
        f"break-even discount={suite.gold.break_even_discount:.2%}, "
        "profitable inside observed envelope="
        f"{suite.gold.profitable_within_observed_envelope}"
    )


if __name__ == "__main__":
    main()
