"""The only place train / validation / test windows are defined.

Windows are by *scheduled departure of the outbound flight* (the booking-relevant clock),
half-open [start, end). Chronological, never random: a random split would train on
February 2025 and test on January 2025, which the pricing could never do.

    FIT    2024-01 .. 2024-12   fit models and baselines
    VALID1 2025-01 .. 2025-03   model selection (hyperparameters, feature ablations)
    VALID2 2025-04 .. 2025-06   calibration only (isotonic fit); never used to pick a model
    VALID  VALID1 + VALID2      inner validation overall
    TRAIN  FIT + VALID          refit window for the final model; all EDA and statistics
    TEST   2025-07 .. 2025-12   touched once, for the backtest (spec: Validation)

Anything that computes a statistic (climatology, historical delay, weights, cell rates)
must filter with `where(...)` on FIT/VALID/TRAIN. Using TEST for exploration counts as leakage.
"""
from __future__ import annotations

WINDOWS = {
    "FIT": ("2024-01-01", "2025-01-01"),
    "VALID1": ("2025-01-01", "2025-04-01"),
    "VALID2": ("2025-04-01", "2025-07-01"),
    "VALID": ("2025-01-01", "2025-07-01"),
    "TRAIN": ("2024-01-01", "2025-07-01"),
    "TEST": ("2025-07-01", "2026-01-01"),
}


def where(window: str, col: str = "out_sched_dep") -> str:
    """SQL predicate selecting one window, e.g. where('TRAIN') for exploration."""
    start, end = WINDOWS[window]
    return f"({col} >= TIMESTAMP '{start}' AND {col} < TIMESTAMP '{end}')"
