"""Confidence scoring (Fig 6c calculateConfidence). The threshold itself lives only in settings."""

from __future__ import annotations


def weighted_confidence(signals: dict[str, float], weights: dict[str, float] | None = None) -> float:
    """Weighted mean of [0, 1] signals. Missing weights default to 1; result is clamped to [0, 1]."""
    if not signals:
        raise ValueError("at least one confidence signal is required")
    total = weight_sum = 0.0
    for name, value in signals.items():
        if value is None:
            continue
        weight = (weights or {}).get(name, 1.0)
        if weight < 0:
            raise ValueError(f"negative weight for {name}")
        total += min(max(float(value), 0.0), 1.0) * weight
        weight_sum += weight
    if weight_sum == 0:
        raise ValueError("all confidence weights are zero")
    return round(total / weight_sum, 4)
