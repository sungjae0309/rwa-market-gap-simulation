"""Reviewed oracle-clamp arithmetic using multiplicative updates."""

from __future__ import annotations

from math import ceil, log

from .common import finite, rate


def minimum_compounded_updates(current: float, target: float, clamp_rate: float) -> int:
    """Minimum multiplicative updates needed to reach ``target`` from ``current``."""

    current = finite(current, "current")
    target = finite(target, "target")
    clamp_rate = rate(clamp_rate, "clamp_rate")
    if current <= 0.0 or target <= 0.0:
        raise ValueError("prices must be positive")
    if clamp_rate == 0.0:
        if current == target:
            return 0
        raise ValueError("a zero clamp rate cannot move the price")
    if current == target:
        return 0
    if target > current:
        return ceil(log(target / current) / log(1.0 + clamp_rate))
    return ceil(log(target / current) / log(1.0 - clamp_rate))
