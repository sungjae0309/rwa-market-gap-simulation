"""Run the public, non-probabilistic commodity simulation."""

from __future__ import annotations

from rwa_market_gap.commodity_simulation import (
    CommoditySimulationEngine,
)
from rwa_market_gap.commodity_simulation.gold import (
    GoldFalsificationResult,
)
from rwa_market_gap.commodity_simulation.market_mechanics import (
    machine_for_market,
)
from rwa_market_gap.commodity_simulation.oracle_math import (
    minimum_compounded_updates,
)


def usd(value: float) -> str:
    return f"${value:,.2f}"


def print_published_mechanics(engine: CommoditySimulationEngine) -> None:
    print("Band identity: published band width vs 1 / max leverage")
    for row in engine.band_identity():
        print(
            f"{row.symbol:9} max leverage={row.max_leverage:g}x, "
            f"band={row.band_rate:.2%}, 1/max={row.inverse_max_leverage:.2%}, "
            f"error={row.identity_error:+.1e}, holds={row.identity_holds}"
        )
    print(
        "The band ceiling equals the bankruptcy move of a max-leverage position."
    )
    print()

    print("Published hard-cap example reproduced by the sequential state machine")
    for direction, monotone_price, expected in (
        ("up", 1_000.0, 15.7625),
        ("down", 0.001, -14.2625),
    ):
        machine = machine_for_market(
            engine.evidence, "WTIOIL", reference_price=100.0
        )
        final = machine.process([monotone_price] * 6)[-1].effective_mark_price
        print(
            f"  monotone {direction:4}: final mark={final:.4f} on a 100.00 anchor "
            f"({final - 100.0:+.4f}%, published {expected:+.4f}%)"
        )
    print()

    print("Which leverage bands the discovery bound actually protects (WTIOIL)")
    for chosen in (20.0, 10.0, 5.0):
        zone = engine.leverage_zone("WTIOIL", chosen)
        protected = "liquidates inside the band" if zone.liquidates_inside_static_band else "protected"
        print(
            f"  {chosen:g}x: maintenance={zone.maintenance_margin_rate:.2%}, "
            f"liquidation move={zone.liquidation_adverse_move:.2%}, "
            f"static band={zone.static_band_rate:.2%} -> {protected}"
        )
    print("  margin tiers were not published and are not modelled")
    print()


def print_hormuz_golden_case(engine: CommoditySimulationEngine) -> None:
    prefix = "events.wti_second_weekend"
    cme_close = float(engine.evidence.value(f"{prefix}.friday_cme_close_usd"))
    observed_mark = float(engine.evidence.value(f"{prefix}.observed_onchain_mark_usd"))
    if not bool(
        engine.evidence.value(
            f"{prefix}.observed_onchain_mark_is_static_upper_bound"
        )
    ):
        raise ValueError(
            "the venue reference cannot be inferred unless the observed mark "
            "is verified as the static upper bound"
        )
    reopen = float(engine.evidence.value(f"{prefix}.cme_reopen_price_usd"))
    wti_spec = {spec.symbol: spec for spec in engine.market_specs()}["WTIOIL"]
    implied_venue_reference = observed_mark / (1.0 + wti_spec.band_rate)
    static = machine_for_market(
        engine.evidence,
        "WTIOIL",
        reference_price=implied_venue_reference,
        reset_limit=0,
    )
    counterfactual = machine_for_market(
        engine.evidence, "WTIOIL", reference_price=implied_venue_reference
    )
    static_cap = static.theoretical_hard_cap("up")
    reanchored_cap = counterfactual.theoretical_hard_cap("up")
    print("Second WTI stress weekend against the published caps")
    print(
        f"  CME comparison close={cme_close:.2f}, implied venue reference="
        f"{implied_venue_reference:.4f}"
    )
    print(
        f"  observed static ceiling={static_cap:.3f}, counterfactual reanchored "
        f"ceiling={reanchored_cap:.3f} (the reanchor shipped after this event)"
    )
    print(
        f"  external reopen={reopen:.2f} exceeds the reanchored ceiling: "
        f"{reopen > reanchored_cap}"
    )
    print()


def main() -> None:
    engine = CommoditySimulationEngine()
    suite = engine.build()

    print_published_mechanics(engine)
    print_hormuz_golden_case(engine)

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
    discount_note: str | None = None
    for exponent in (0.5, 1.0, 2.0):
        result = suite.gold.with_impact_exponent(exponent).analyze()
        if not isinstance(result, GoldFalsificationResult):
            raise AssertionError("stale-oracle state should be executable")
        discount_note = result.tested_discount_source
        print(
            f"impact exponent={exponent:.1f}, "
            f"break-even discount={result.modelled_break_even_discount:.2%}, "
            f"tested discount assumption={result.tested_discount_assumption:.2%}, "
            f"net={usd(result.ledger.net_profit_usd)}, "
            f"profitable={result.profitable_at_tested_discount}"
        )
    print(f"discount note: {discount_note}")
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

    # The binding clamp is the tighter of the protocol and relayer limits, and
    # the target move is the recognition gap of the second stress weekend. Both
    # come from the ledger rather than being restated as literals here.
    binding_clamp = min(
        float(engine.evidence.value("mechanics.protocol_update_clamp_rate")),
        float(engine.evidence.value("mechanics.relayer_update_clamp_rate")),
    )
    recognition_gap = suite.wti.analyze(
        "wti_second_weekend"
    ).signed_price_recognition_gap_rate
    updates = minimum_compounded_updates(1.0, 1.0 + recognition_gap, binding_clamp)
    print(
        f"Compounded {binding_clamp:.1%} updates for a {recognition_gap:.3%} "
        f"recognition gap: {updates}"
    )


if __name__ == "__main__":
    main()
