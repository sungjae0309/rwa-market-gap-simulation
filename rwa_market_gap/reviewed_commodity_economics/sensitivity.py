"""One-at-a-time sensitivity sweeps for every reviewed C-grade assumption."""

from __future__ import annotations

from dataclasses import dataclass, replace

from rwa_market_gap.commodity_oracle.evidence import EvidenceRecord, VerifiedInputLedger

from .gold import GoldFalsificationEconomics, GoldFalsificationResult
from .wti import WTIStressEconomics


WTI_ASSUMPTION_MAP = {
    "wti.requested_notional_usd": "requested_notional_usd",
    "wti.assumed_capacity_usd": "assumed_capacity_usd",
    "wti.allocated_margin_usd": "allocated_margin_usd",
    "wti.round_trip_fee_rate": "round_trip_fee_rate",
    "wti.round_trip_slippage_rate": "round_trip_slippage_rate",
    "wti.slippage_exponent": "slippage_exponent",
    "wti.signed_funding_rate_over_horizon": "signed_funding_rate_over_horizon",
    "wti.capital_annual_rate": "capital_annual_rate",
}

GOLD_ASSUMPTION_MAP = {
    "gold.requested_borrow_usd": "requested_borrow_usd",
    "gold.acquisition_fee_rate": "acquisition_fee_rate",
    "gold.borrow_interest_rate_over_horizon": "borrow_interest_rate_over_horizon",
    "gold.gas_and_operations_usd": "gas_and_operations_usd",
    "gold.impact_exponent": "impact_exponent",
}


@dataclass(frozen=True)
class SensitivityPoint:
    model: str
    parameter: str
    case: str
    value: float
    net_profit_usd: float
    break_even_rate: float
    inactive_reason: str | None = None


def _wti_inactive_reason(path: str, result) -> str | None:
    """Explain a parameter that cannot move the result in a given state.

    A flat sweep row is ambiguous on its own: it can mean the parameter does
    not matter, or that the base state happens to sit where the parameter has
    no purchase. These two cases are distinguished explicitly so the printed
    table is not read as "this assumption is irrelevant".
    """

    capacity = result.capacity
    if path == "wti.slippage_exponent" and (
        capacity.executable_notional_usd >= capacity.assumed_capacity_usd
    ):
        return (
            "executable notional sits on the capacity reference, so utilization "
            "is 1.0 and any exponent cancels; the curve shape is active only "
            "below capacity"
        )
    return None


def _bounds(record: EvidenceRecord) -> tuple[float, float]:
    if record.grade != "C" or record.label != "assumption":
        raise ValueError(f"{record.path} is not a C-grade assumption")
    if record.sensitivity is None:
        raise ValueError(f"{record.path} has no sensitivity bounds")
    return record.sensitivity


def wti_one_at_a_time(
    model: WTIStressEconomics,
    inputs: VerifiedInputLedger,
    *,
    event: str = "wti_second_weekend",
) -> tuple[SensitivityPoint, ...]:
    points: list[SensitivityPoint] = []
    for path, attribute in WTI_ASSUMPTION_MAP.items():
        record = inputs.record(path)
        low, high = _bounds(record)
        for case, value in (("low", low), ("base", float(record.value)), ("high", high)):
            assumptions = replace(model.assumptions, **{attribute: value})
            result = WTIStressEconomics(model.evidence, assumptions).analyze(event)
            points.append(
                SensitivityPoint(
                    model="wti",
                    parameter=path,
                    case=case,
                    value=value,
                    net_profit_usd=result.ledger.net_profit_usd,
                    break_even_rate=result.break_even_positive_return_rate,
                    inactive_reason=_wti_inactive_reason(path, result),
                )
            )
    return tuple(points)


def gold_one_at_a_time(
    model: GoldFalsificationEconomics,
    inputs: VerifiedInputLedger,
) -> tuple[SensitivityPoint, ...]:
    points: list[SensitivityPoint] = []
    for path, attribute in GOLD_ASSUMPTION_MAP.items():
        record = inputs.record(path)
        low, high = _bounds(record)
        for case, value in (("low", low), ("base", float(record.value)), ("high", high)):
            assumptions = replace(model.assumptions, **{attribute: value})
            result = GoldFalsificationEconomics(model.evidence, assumptions).analyze()
            if not isinstance(result, GoldFalsificationResult):
                raise AssertionError("stale-oracle state should be executable")
            points.append(
                SensitivityPoint(
                    model="gold",
                    parameter=path,
                    case=case,
                    value=value,
                    net_profit_usd=result.ledger.net_profit_usd,
                    break_even_rate=result.modelled_break_even_discount,
                )
            )
    return tuple(points)
