"""Print one-at-a-time sensitivity ranges for every model assumption."""

from __future__ import annotations

from collections import defaultdict

from rwa_market_gap.commodity_simulation import (
    CommoditySimulationEngine,
)
from rwa_market_gap.commodity_simulation.sensitivity import (
    SensitivityPoint,
    gold_one_at_a_time,
    wti_one_at_a_time,
)


def print_ranges(points: tuple[SensitivityPoint, ...]) -> None:
    grouped: dict[str, list[SensitivityPoint]] = defaultdict(list)
    for point in points:
        grouped[point.parameter].append(point)
    for parameter, rows in grouped.items():
        min_net = min(row.net_profit_usd for row in rows)
        max_net = max(row.net_profit_usd for row in rows)
        min_break_even = min(row.break_even_rate for row in rows)
        max_break_even = max(row.break_even_rate for row in rows)
        print(
            f"{parameter}: net ${min_net:,.2f}..${max_net:,.2f}, "
            f"break-even {min_break_even:.3%}..{max_break_even:.3%}"
        )
        reasons = {row.inactive_reason for row in rows if row.inactive_reason}
        if min_net == max_net and reasons:
            for reason in sorted(reasons):
                print(f"    inactive at this configuration: {reason}")


def main() -> None:
    engine = CommoditySimulationEngine()
    suite = engine.build()
    print("WTI one-at-a-time sensitivity")
    print_ranges(wti_one_at_a_time(suite.wti, engine.assumptions))
    print()
    print("Gold one-at-a-time sensitivity")
    print_ranges(gold_one_at_a_time(suite.gold, engine.assumptions))


if __name__ == "__main__":
    main()
