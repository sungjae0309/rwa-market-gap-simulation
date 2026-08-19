"""Run the reviewed, non-probabilistic commodity economics package."""

from __future__ import annotations

from rwa_market_gap.reviewed_commodity_economics import (
    ReviewedCommodityEconomicsEngine,
)
from rwa_market_gap.reviewed_commodity_economics.gold import (
    GoldFalsificationResult,
)
from rwa_market_gap.reviewed_commodity_economics.oracle_math import (
    minimum_compounded_updates,
)


def usd(value: float) -> str:
    return f"${value:,.2f}"


def main() -> None:
    suite = ReviewedCommodityEconomicsEngine().build()

    print("WTI observed stress states (not attack probabilities)")
    for result in suite.wti.analyze_all():
        print(
            f"{result.event}: return={result.position_return_rate:.2%}, "
            f"PfC={usd(result.ledger.pfc_usd)}, CoC={usd(result.ledger.coc_usd)}, "
            f"net={usd(result.ledger.net_profit_usd)}, "
            f"break-even={result.break_even_positive_return_rate:.3%}"
        )
        print(
            f"  requested={usd(result.capacity.requested_notional_usd)}, "
            f"executable={usd(result.capacity.executable_notional_usd)}, "
            f"capacity assumption={usd(result.capacity.assumed_capacity_usd)}, "
            "success_probability=None"
        )
        headroom = (
            result.break_even_funding_rate_over_horizon
            / result.assumed_funding_rate_over_horizon
            if result.assumed_funding_rate_over_horizon > 0.0
            else float("inf")
        )
        print(
            "  funding break-even="
            f"{result.break_even_funding_rate_over_horizon:.3%}/"
            f"{result.holding_horizon_hours:g}h "
            f"(simple hourly average "
            f"{result.simple_average_break_even_funding_rate_per_hour:.4%}), "
            f"assumed={result.assumed_funding_rate_over_horizon:.3%}/"
            f"{result.holding_horizon_hours:g}h, "
            f"ratio={headroom:.1f}x, "
            f"inside declared sensitivity="
            f"{result.break_even_funding_within_declared_sensitivity}"
        )
    print()

    print("Funding is the mechanism that prices this basis away.")
    print(
        "The state stops paying above the break-even funding rate; whether real "
        "venue funding reached it is NOT established by this model."
    )
    print()

    print("WTI size sensitivity with a fixed, unverified capacity assumption")
    for requested in (100_000.0, 1_000_000.0, 10_000_000.0):
        result = suite.wti.with_requested_notional(requested).analyze(
            "wti_second_weekend"
        )
        print(
            f"requested={usd(requested)}, "
            f"executable={usd(result.capacity.executable_notional_usd)}, "
            f"net={usd(result.ledger.net_profit_usd)}"
        )
    print()

    print("Tokenized-gold structural falsification")
    for exponent in (0.5, 1.0, 2.0):
        result = suite.gold.with_impact_exponent(exponent).analyze()
        if not isinstance(result, GoldFalsificationResult):
            raise AssertionError("stale-oracle state should be executable")
        print(
            f"impact exponent={exponent:.1f}, "
            f"break-even discount={result.modelled_break_even_discount:.2%}, "
            f"observed discount={result.observed_discount:.2%}, "
            f"net={usd(result.ledger.net_profit_usd)}, "
            f"profitable={result.profitable_at_observed_discount}"
        )
    print(
        "liquidity note: the reported sell-side average-impact bound is used as "
        "a conservative proxy for buy-side acquisition cost"
    )
    print("success_probability=None (stale state is a condition, not a distribution)")
    print()

    gas = suite.natural_gas.analyze()
    print("Natural-gas evidence status")
    print(
        f"raw change difference={gas.raw_change_difference:.1%}p, "
        f"event window verified={gas.event_window_verified}, "
        f"dollar loss={gas.aligned_tracking_error_usd}, "
        f"attack probability={gas.attack_success_probability}"
    )
    print()

    updates = minimum_compounded_updates(1.0, 1.12104, 0.005)
    print(f"Compounded 0.5% updates for a 12.104% target move: {updates}")


if __name__ == "__main__":
    main()
