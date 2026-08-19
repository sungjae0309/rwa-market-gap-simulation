"""Typed market specifications assembled from the evidence ledger."""

from __future__ import annotations

from dataclasses import dataclass

from .evidence import VerifiedInputLedger
from .margin import MarginMode


@dataclass(frozen=True)
class MarketSpec:
    symbol: str
    feed: str
    max_leverage: float
    band_rate: float
    reset_limit: int
    margin_mode: MarginMode
    external_session: str

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not self.feed.strip():
            raise ValueError("symbol and feed must not be blank")
        if self.max_leverage <= 0.0:
            raise ValueError("max_leverage must be positive")
        if not 0.0 < self.band_rate < 1.0:
            raise ValueError("band_rate must be in (0, 1)")
        if self.reset_limit < 0:
            raise ValueError("reset_limit must be non-negative")
        if self.margin_mode not in {"cross", "isolated"}:
            raise ValueError("margin_mode must be cross or isolated")
        if not self.external_session.strip():
            raise ValueError("external_session must not be blank")

    @property
    def band_identity_error(self) -> float:
        return self.band_rate - 1.0 / self.max_leverage

    @property
    def upward_hard_cap_rate(self) -> float:
        return (1.0 + self.band_rate) ** (self.reset_limit + 1) - 1.0

    @property
    def downward_hard_cap_rate(self) -> float:
        return 1.0 - (1.0 - self.band_rate) ** (self.reset_limit + 1)

    @property
    def has_backstop_liquidator(self) -> bool:
        return self.margin_mode == "cross"

    @classmethod
    def from_ledger(cls, ledger: VerifiedInputLedger, symbol: str) -> "MarketSpec":
        prefix = f"markets.{symbol}"
        return cls(
            symbol=symbol,
            feed=str(ledger.value(f"{prefix}.feed")),
            max_leverage=float(ledger.value(f"{prefix}.max_leverage")),
            band_rate=float(ledger.value(f"{prefix}.band_rate")),
            reset_limit=int(ledger.value(f"{prefix}.reset_limit")),
            margin_mode=str(ledger.value(f"{prefix}.margin_mode")),
            external_session=str(ledger.value(f"{prefix}.external_session")),
        )
