"""Natural-gas evidence classification with explicit event-window gating."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .common import finite, non_negative
from .evidence import VerifiedInputLedger


@dataclass(frozen=True)
class NaturalGasReviewResult:
    classification: str
    classified_as_attack: bool
    jkm_change: float
    henry_hub_change: float
    raw_change_difference: float
    event_window_verified: bool
    event_window_start: date | None
    event_window_end: date | None
    aligned_tracking_error_usd: float | None
    attack_success_probability: None = None
    reason: str = (
        "No adversarial control action converts the benchmark mismatch into a "
        "protocol loss in the supplied evidence."
    )


class NaturalGasEvidenceReview:
    def __init__(self, evidence: VerifiedInputLedger) -> None:
        self.evidence = evidence

    def analyze(
        self,
        *,
        exposure_notional_usd: float | None = None,
    ) -> NaturalGasReviewResult:
        prefix = "events.natural_gas_benchmark_gap"
        event_window_start = self._optional_evidence_date(
            f"{prefix}.event_window_start"
        )
        event_window_end = self._optional_evidence_date(
            f"{prefix}.event_window_end"
        )
        if (event_window_start is None) != (event_window_end is None):
            raise ValueError("verified event-window start and end must both exist")
        if event_window_start is not None and event_window_end < event_window_start:
            raise ValueError("verified event-window end precedes start")
        if exposure_notional_usd is not None:
            non_negative(exposure_notional_usd, "exposure_notional_usd")
            if event_window_start is None:
                raise ValueError(
                    "a dollar tracking error requires a verified event window"
                )
        jkm = finite(float(self.evidence.value(f"{prefix}.jkm_change")), "jkm")
        henry = finite(
            float(self.evidence.value(f"{prefix}.henry_hub_change")), "henry_hub"
        )
        gap = jkm - henry
        window_verified = event_window_start is not None
        aligned_error = (
            exposure_notional_usd * gap
            if window_verified and exposure_notional_usd is not None
            else None
        )
        return NaturalGasReviewResult(
            classification="benchmark mismatch; not an attack model",
            classified_as_attack=False,
            jkm_change=jkm,
            henry_hub_change=henry,
            raw_change_difference=gap,
            event_window_verified=window_verified,
            event_window_start=event_window_start,
            event_window_end=event_window_end,
            aligned_tracking_error_usd=aligned_error,
        )

    def _optional_evidence_date(self, path: str) -> date | None:
        try:
            value = self.evidence.value(path)
        except KeyError:
            return None
        if not isinstance(value, str):
            raise TypeError(f"{path} must contain an ISO date string")
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise ValueError(f"{path} must contain an ISO date") from error
