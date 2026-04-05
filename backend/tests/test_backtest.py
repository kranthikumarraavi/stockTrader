# Backtest tests
"""Tests for backtester and simulator."""

import numpy as np
import pandas as pd
import pytest

from backend.prediction_engine.backtest.backtester import Backtester, ExecutionConfig
from backend.trading_engine.simulator import PaperSimulator, OrderIntent
from backend.api.routers.backtest import _build_execution_predictions


# ---------------------------------------------------------------------------
# Backtester
# ---------------------------------------------------------------------------

def test_backtester_basic():
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=10, freq="B")

    predictions = pd.DataFrame({
        "date": dates,
        "ticker": "TEST",
        "action": ["buy"] * 5 + ["sell"] * 5,
        "confidence": 0.8,
    })
    prices = pd.DataFrame({
        "Date": dates,
        "ticker": "TEST",
        "Close": np.linspace(100, 110, 10),
    })

    bt = Backtester(ExecutionConfig(slippage_pct=0, commission_per_trade=0, fill_probability=1.0))
    result = bt.run(predictions, prices, initial_capital=100_000.0)

    assert result.status == "completed"
    assert result.initial_capital == 100_000.0
    assert result.final_value > 0
    assert len(result.trades) > 0


def test_backtester_metrics():
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=20, freq="B")

    predictions = pd.DataFrame({
        "date": dates,
        "ticker": "TEST",
        "action": (["buy"] * 10 + ["sell"] * 10),
        "confidence": 0.8,
    })
    prices = pd.DataFrame({
        "Date": dates,
        "ticker": "TEST",
        "Close": np.linspace(100, 120, 20),
    })

    bt = Backtester(ExecutionConfig(fill_probability=1.0))
    result = bt.run(predictions, prices)

    assert result.sharpe_ratio is not None or result.max_drawdown_pct is not None


def test_build_execution_predictions_shifts_to_next_bar():
    features_df = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-01", "2026-01-02"]
            ),
            "ticker": ["AAA", "AAA", "AAA", "BBB", "BBB"],
            "atr_14": [1.1, 1.2, 1.3, 0.9, 1.0],
            "volatility_20": [0.2, 0.21, 0.22, 0.18, 0.19],
        }
    )
    preds_raw = [
        {"action": "buy", "confidence": 0.8},
        {"action": "hold", "confidence": 0.5},
        {"action": "sell", "confidence": 0.7},
        {"action": "buy", "confidence": 0.75},
        {"action": "sell", "confidence": 0.65},
    ]

    shifted = _build_execution_predictions(features_df, preds_raw)

    # One row dropped per ticker due to next-bar execution mapping.
    assert len(shifted) == len(features_df) - features_df["ticker"].nunique()
    assert (shifted["date"] > shifted["signal_date"]).all()

    aaa_rows = shifted[shifted["ticker"] == "AAA"].sort_values("signal_date")
    assert list(aaa_rows["signal_date"].dt.strftime("%Y-%m-%d")) == ["2026-01-01", "2026-01-02"]
    assert list(aaa_rows["date"].dt.strftime("%Y-%m-%d")) == ["2026-01-02", "2026-01-03"]


def test_build_execution_predictions_rejects_length_mismatch():
    features_df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
            "ticker": ["AAA", "AAA"],
        }
    )
    with pytest.raises(ValueError):
        _build_execution_predictions(features_df, [{"action": "buy", "confidence": 0.8}])


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------

def test_simulator_buy_and_sell():
    sim = PaperSimulator(slippage_pct=0, commission=0, initial_capital=100_000)

    # Buy
    intent = OrderIntent(ticker="TEST", side="buy", quantity=10, order_type="market")
    fill = sim.execute_intent(intent, market_price=100.0)
    assert fill is not None
    assert fill.side == "buy"
    assert sim.positions["TEST"] == 10

    # Sell
    intent = OrderIntent(ticker="TEST", side="sell", quantity=10, order_type="market")
    fill = sim.execute_intent(intent, market_price=110.0)
    assert fill is not None
    assert fill.side == "sell"
    assert sim.positions["TEST"] == 0


def test_simulator_insufficient_funds():
    sim = PaperSimulator(initial_capital=50)
    intent = OrderIntent(ticker="TEST", side="buy", quantity=100, order_type="market")
    fill = sim.execute_intent(intent, market_price=100.0)
    assert fill is None


def test_simulator_audit_log():
    sim = PaperSimulator(initial_capital=100_000)
    intent = OrderIntent(ticker="TEST", side="buy", quantity=1, order_type="market")
    sim.execute_intent(intent, market_price=100.0)
    log = sim.export_audit_log()
    assert len(log) >= 2  # ORDER_RECEIVED + ORDER_FILLED
    assert log[0]["event"] == "ORDER_RECEIVED"


def test_simulator_replay_day():
    sim = PaperSimulator(initial_capital=100_000, slippage_pct=0, commission=0)
    intents = [
        OrderIntent(ticker="A", side="buy", quantity=5, order_type="market"),
        OrderIntent(ticker="B", side="buy", quantity=5, order_type="market"),
    ]
    prices = {"A": 100.0, "B": 200.0}
    fills = sim.replay_day(intents, prices)
    assert len(fills) == 2
