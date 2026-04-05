# Training pipeline safety tests
"""Tests for safe walk-forward split and structured insufficient-data errors."""

from __future__ import annotations

import pandas as pd
import pytest

from backend.prediction_engine.training.trainer import (
    TrainingConfig,
    TrainingPipelineError,
    _walk_forward_split,
)


def _make_labeled_rows(
    *,
    unique_dates: int,
    tickers: tuple[str, ...] = ("AAA", "BBB", "CCC"),
) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=unique_dates, freq="B")
    rows: list[dict] = []
    for ticker in tickers:
        for i, dt in enumerate(dates):
            rows.append(
                {
                    "date": dt,
                    "ticker": ticker,
                    "label": i % 2,
                }
            )
    return pd.DataFrame(rows)


def test_walk_forward_split_fails_with_structured_insufficient_data():
    df = _make_labeled_rows(unique_dates=27)
    cfg = TrainingConfig(
        train_min_days=20,
        val_min_days=5,
        test_min_days=5,
        purge_gap_days=1,
        min_unique_dates=60,
        min_rows_per_symbol=1,
        min_symbols=1,
        min_samples_per_class=1,
    )

    with pytest.raises(TrainingPipelineError) as exc_info:
        _walk_forward_split(df, config=cfg)

    err = exc_info.value
    assert err.reason == "insufficient_data"
    assert err.details["unique_dates"] == 27
    assert err.details["required_min_dates"] >= 60


def test_walk_forward_split_is_time_ordered_and_non_overlapping():
    df = _make_labeled_rows(unique_dates=160)
    cfg = TrainingConfig(
        train_min_days=90,
        val_min_days=20,
        test_min_days=20,
        purge_gap_days=3,
        min_unique_dates=130,
        min_rows_per_symbol=1,
        min_symbols=1,
        min_samples_per_class=1,
    )

    train_df, val_df, test_df = _walk_forward_split(df, config=cfg)

    assert not train_df.empty
    assert not val_df.empty
    assert not test_df.empty
    assert train_df["date"].max() < val_df["date"].min()
    assert val_df["date"].max() < test_df["date"].min()

    unique_dates = pd.Index(sorted(df["date"].unique()))
    train_end = unique_dates.get_loc(train_df["date"].max())
    val_start = unique_dates.get_loc(val_df["date"].min())
    val_end = unique_dates.get_loc(val_df["date"].max())
    test_start = unique_dates.get_loc(test_df["date"].min())

    assert (val_start - train_end - 1) >= cfg.purge_gap_days
    assert (test_start - val_end - 1) >= cfg.purge_gap_days
