"""Run the evidence-driven commodity oracle scenarios."""

from rwa_market_gap.commodity_oracle.scenarios import CommodityOracleScenarioEngine


def money(value: float) -> str:
    return f"${value:,.2f}"


def main() -> None:
    engine = CommodityOracleScenarioEngine()
    result = engine.run_all()

    print("WTI time gap")
    print(
        f"recognized={result.wti.onchain_recognized_move:.2%}, "
        f"reopen={result.wti.actual_reopen_move:.2%}, "
        "unrecognized="
        f"{result.wti.unrecognized_gap_percentage_points:.2%}p"
    )
    print(
        f"counterfactual v2 cap={result.wti.counterfactual_v2_cap_rate:.2%}, "
        f"minimum clamped updates={result.wti.minimum_clamped_updates}, "
        f"short/long liquidations={result.wti.short_to_long_liquidation_ratio:.2f}x"
    )
    print(f"ADL confirmed by supplied evidence: {result.wti.adl_was_confirmed}")

    print("\nNatural-gas benchmark gap")
    print(
        f"JKM={result.natural_gas.target_change:.1%}, "
        f"Henry Hub={result.natural_gas.proxy_change:.1%}, "
        f"gap={result.natural_gas.benchmark_gap_percentage_points:.1%}p"
    )
    print(
        f"illustrative proxy-hedge shortfall on "
        f"{money(result.natural_gas.exposure_notional_usd)}="
        f"{money(result.natural_gas.proxy_hedge_shortfall_usd)}"
    )

    print("\nTokenized-gold hierarchy gap")
    print(
        f"liquidation start={result.gold.liquidation_start_gap:.2%}, "
        f"protocol insolvency buffer={result.gold.protocol_insolvency_buffer:.2%}"
    )
    print(
        f"bonus residual at observed discount="
        f"{result.gold.liquidator_residual_margin:.2%}, "
        f"secondary-holder redemption={result.gold.secondary_holder_can_redeem}"
    )
    print(
        f"debt cap/capacity={result.gold.debt_cap_to_capacity:.2%}, "
        "time-aligned supply cap/capacity="
        f"{result.gold.supply_cap_to_capacity:.2f}x"
    )


if __name__ == "__main__":
    main()
