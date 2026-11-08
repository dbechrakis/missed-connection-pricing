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

v2 (developed after H2 2025 was spent, see VALIDATION.md Part 3). H2 2025 is now ordinary
development data, so v2 may train and select on it with a *new* chronological scheme:

    S_FIT   2024-01 .. 2025-03   selection experiment: fit the GBM here
    S_EVAL  2025-07 .. 2025-12   selection experiment: walk-forward pricing, one month at a time
                                  (the calibrator for month m sees only months before m, from 2025-04)
    V2_FIT  2024-01 .. 2025-09   final v2 GBM and route statistics
    V2_CAL  2025-10 .. 2025-12   static v2 calibrator (out-of-sample for the GBM)
    HOLDOUT 2026-01 .. 2026-08   never read before the pre-registered run; the clean test of v1 and v2
                                  (ends 2026-08-30 exclusive: the data stops on the 31st, so the last
                                  days cannot see their next flight)

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
    "S_FIT": ("2024-01-01", "2025-04-01"),
    "S_EVAL": ("2025-07-01", "2026-01-01"),
    "V2_FIT": ("2024-01-01", "2025-10-01"),
    "V2_CAL": ("2025-10-01", "2026-01-01"),
    "HOLDOUT": ("2026-01-01", "2026-08-30"),
}


def where(window: str, col: str = "out_sched_dep") -> str:
    """SQL predicate selecting one window, e.g. where('TRAIN') for exploration."""
    start, end = WINDOWS[window]
    return f"({col} >= TIMESTAMP '{start}' AND {col} < TIMESTAMP '{end}')"
