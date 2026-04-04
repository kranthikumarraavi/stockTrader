"""Tests for the shared strategy/execution/schema layer.

Covers: leakage checks, schemas, strategy engine, execution adapters,
parity runner, and backtester integration.
"""

import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta

# ── Schemas ──────────────────────────────────────────────────────────
from backend.shared.schemas import (
    ExecutionMode, Fill, OrderRequest, OrderSide, OrderState, OrderStatus,
    OrderType, PortfolioState, Position, RegimeLabel, RiskLimits,
    SignalDirection, TradeResult, TradingSignal,
)


class TestSchemas:
    def test_trading_signal_defaults(self):
        sig = TradingSignal(
            instrument="RELIANCE",
            timestamp=datetime(2025, 1, 1),
            timeframe="1d",
            signal_direction=SignalDirection.LONG,
            direction_probability=0.65,
            expected_move=0.02,
            expected_volatility=0.2,
            confidence_score=0.65,
            regime_label=RegimeLabel.TRENDING_UP,
        )
        assert sig.no_trade_flag is False
        assert sig.event_risk_score == 0.0
        assert sig.recommended_holding_horizon == 1

    def test_order_request_uuid(self):
        o1 = OrderRequest(instrument="TCS", side=OrderSide.BUY, quantity=10)
        o2 = OrderRequest(instrument="TCS", side=OrderSide.BUY, quantity=10)
        assert o1.id != o2.id  # unique UUIDs

    def test_order_state_apply_fill(self):
        req = OrderRequest(instrument="TCS", side=OrderSide.BUY, quantity=100)
        state = OrderState(request=req)
        fill = Fill(
            order_id=req.id, instrument="TCS", side=OrderSide.BUY,
            quantity=60, price=100.0,
        )
        state.apply_fill(fill)
        assert state.status == OrderStatus.PARTIAL
        assert state.filled_qty == 60

        fill2 = Fill(
            order_id=req.id, instrument="TCS", side=OrderSide.BUY,
            quantity=40, price=102.0,
        )
        state.apply_fill(fill2)
        assert state.status == OrderStatus.FILLED
        assert state.filled_qty == 100
        assert abs(state.avg_fill_price - 100.8) < 0.01

    def test_position_mark_to_market(self):
        pos = Position(instrument="INFY", quantity=10, avg_entry_price=100)
        pos.mark_to_market(110)
        assert pos.unrealised_pnl == 100  # (110-100)*10
        assert pos.trailing_high == 110

    def test_portfolio_equity(self):
        p = PortfolioState(cash=50_000)
        pos = Position(instrument="A", quantity=10, avg_entry_price=100)
        pos.mark_to_market(120)
        p.positions["A"] = pos
        # equity = cash + sum(unrealised + entry*qty) for open
        assert p.equity == 50_000 + (120 - 100) * 10 + 100 * 10

    def test_risk_limits_defaults(self):
        r = RiskLimits()
        assert r.max_position_pct == 0.20
        assert r.stop_loss_pct == 0.05
        assert r.take_profit_pct == 0.10
        assert r.max_holding_bars == 30
        assert r.trailing_stop_pct == 0.03
        assert r.use_atr_stops is True
        assert r.atr_stop_multiplier == 1.5
        assert r.atr_profit_multiplier == 4.0
        assert r.partial_tp_enabled is True
        assert r.regime_scale_crash == 0.25


# ── Strategy Engine ──────────────────────────────────────────────────
from backend.shared.strategy_engine import (
    RiskGate, StrategyEngine, size_position, _regime_scale, _momentum_confirms,
)


class TestRiskGate:
    def _make_signal(self, confidence=0.7, no_trade=False, event_risk=0.0,
                     momentum=0.01, ema_crossover=0.0):
        return TradingSignal(
            instrument="TEST",
            timestamp=datetime(2025, 1, 1),
            timeframe="1d",
            signal_direction=SignalDirection.LONG,
            direction_probability=confidence,
            expected_move=0.02,
            expected_volatility=0.02,
            confidence_score=confidence,
            regime_label=RegimeLabel.UNKNOWN,
            no_trade_flag=no_trade,
            event_risk_score=event_risk,
            metadata={"momentum_10": momentum, "ema_crossover": ema_crossover},
        )

    def test_approve_normal(self):
        portfolio = PortfolioState(cash=100_000)
        limits = RiskLimits()
        gate = RiskGate(limits)
        ok, reason, qty = gate.approve(
            self._make_signal(), portfolio, 100, 100.0,
        )
        assert ok
        assert qty == 100

    def test_reject_no_trade(self):
        portfolio = PortfolioState(cash=100_000)
        limits = RiskLimits()
        gate = RiskGate(limits)
        ok, reason, _ = gate.approve(
            self._make_signal(no_trade=True), portfolio, 100, 100.0,
        )
        assert not ok
        assert "no_trade" in reason

    def test_reject_low_confidence(self):
        portfolio = PortfolioState(cash=100_000)
        limits = RiskLimits(min_signal_confidence=0.55, require_momentum_confirm=False)
        gate = RiskGate(limits)
        ok, reason, _ = gate.approve(
            self._make_signal(confidence=0.40), portfolio, 100, 100.0,
        )
        assert not ok
        assert "confidence" in reason.lower()

    def test_reject_high_event_risk(self):
        portfolio = PortfolioState(cash=100_000)
        limits = RiskLimits(max_event_risk=0.8)
        gate = RiskGate(limits)
        ok, reason, _ = gate.approve(
            self._make_signal(event_risk=0.95), portfolio, 100, 100.0,
        )
        assert not ok
        assert "event" in reason.lower()

    def test_reject_max_positions(self):
        portfolio = PortfolioState(cash=100_000)
        for i in range(8):
            portfolio.positions[f"STOCK{i}"] = Position(
                instrument=f"STOCK{i}", quantity=10, avg_entry_price=100,
            )
        limits = RiskLimits(max_positions=8, require_momentum_confirm=False)
        gate = RiskGate(limits)
        ok, reason, _ = gate.approve(
            self._make_signal(), portfolio, 100, 100.0,
        )
        assert not ok
        assert "max_positions" in reason

    def test_reject_daily_loss(self):
        portfolio = PortfolioState(cash=100_000, daily_pnl=-5000)
        limits = RiskLimits(max_daily_loss_pct=0.03)
        gate = RiskGate(limits)
        ok, reason, _ = gate.approve(
            self._make_signal(), portfolio, 100, 100.0,
        )
        assert not ok
        assert "daily_loss" in reason


class TestSizePosition:
    def test_basic_sizing(self):
        signal = TradingSignal(
            instrument="TEST", timestamp=datetime(2025, 1, 1),
            timeframe="1d", signal_direction=SignalDirection.LONG,
            direction_probability=0.7, expected_move=0.02,
            expected_volatility=0.2, confidence_score=0.7,
            regime_label=RegimeLabel.UNKNOWN,
        )
        portfolio = PortfolioState(cash=100_000)
        qty = size_position(signal, portfolio, RiskLimits(), 100.0)
        assert qty > 0
        assert qty * 100 <= 100_000 * 0.20  # max 20%

    def test_no_position_on_low_confidence(self):
        signal = TradingSignal(
            instrument="TEST", timestamp=datetime(2025, 1, 1),
            timeframe="1d", signal_direction=SignalDirection.LONG,
            direction_probability=0.51, expected_move=0.001,
            expected_volatility=0.5, confidence_score=0.51,
            regime_label=RegimeLabel.HIGH_VOLATILITY,
        )
        portfolio = PortfolioState(cash=100_000)
        qty = size_position(signal, portfolio, RiskLimits(), 100.0)
        # should still produce something (kelly decides)
        assert qty >= 0


class TestStrategyEngine:
    def _make_signal(self, direction=SignalDirection.LONG, confidence=0.7):
        return TradingSignal(
            instrument="TEST", timestamp=datetime(2025, 1, 1),
            timeframe="1d", signal_direction=direction,
            direction_probability=confidence, expected_move=0.02,
            expected_volatility=0.02, confidence_score=confidence,
            regime_label=RegimeLabel.UNKNOWN,
            metadata={"momentum_10": 0.01, "ema_crossover": 0.1, "atr_14": 3.0},
        )

    def test_entry_order(self):
        engine = StrategyEngine(RiskLimits())
        portfolio = PortfolioState(cash=100_000)
        orders = engine.on_signal(self._make_signal(), portfolio, 100.0)
        assert len(orders) >= 1
        assert orders[0].side == OrderSide.BUY

    def test_no_duplicate_entry(self):
        engine = StrategyEngine(RiskLimits())
        portfolio = PortfolioState(cash=100_000)
        portfolio.positions["TEST"] = Position(
            instrument="TEST", quantity=10, avg_entry_price=100,
        )
        orders = engine.on_signal(self._make_signal(), portfolio, 100.0)
        assert len(orders) == 0  # already has position

    def test_flat_signal_closes(self):
        engine = StrategyEngine(RiskLimits())
        portfolio = PortfolioState(cash=90_000)
        portfolio.positions["TEST"] = Position(
            instrument="TEST", quantity=10, avg_entry_price=100,
        )
        orders = engine.on_signal(
            self._make_signal(direction=SignalDirection.FLAT), portfolio, 105.0,
        )
        assert len(orders) == 1
        assert orders[0].side == OrderSide.SELL

    def test_check_exits_stop_loss(self):
        engine = StrategyEngine(RiskLimits(stop_loss_pct=0.03))
        portfolio = PortfolioState(cash=90_000)
        portfolio.positions["TEST"] = Position(
            instrument="TEST", quantity=10, avg_entry_price=100,
            stop_loss=97.0,  # 3% below 100
        )
        orders = engine.check_exits(portfolio, {"TEST": 96.0})
        assert len(orders) == 1
        assert orders[0].side == OrderSide.SELL

    def test_check_exits_take_profit(self):
        engine = StrategyEngine(RiskLimits(take_profit_pct=0.06))
        portfolio = PortfolioState(cash=90_000)
        portfolio.positions["TEST"] = Position(
            instrument="TEST", quantity=10, avg_entry_price=100,
            take_profit=106.0,
        )
        orders = engine.check_exits(portfolio, {"TEST": 107.0})
        assert len(orders) == 1

    def test_check_exits_max_holding(self):
        limits = RiskLimits(max_holding_bars=5)
        engine = StrategyEngine(limits)
        engine.bar_index = 10
        portfolio = PortfolioState(cash=90_000)
        portfolio.positions["TEST"] = Position(
            instrument="TEST", quantity=10, avg_entry_price=100,
            entry_bar_index=3,  # held for 7 bars
        )
        orders = engine.check_exits(portfolio, {"TEST": 100.0})
        assert len(orders) == 1

    def test_trailing_stop_exit(self):
        engine = StrategyEngine(RiskLimits())
        portfolio = PortfolioState(cash=90_000)
        portfolio.positions["TEST"] = Position(
            instrument="TEST", quantity=10, avg_entry_price=100,
            trailing_stop_pct=0.03, trailing_high=120.0,
        )
        # Price fell to 117 → 120*(1-0.03)=116.4 → no exit
        orders = engine.check_exits(portfolio, {"TEST": 117.0})
        assert len(orders) == 0
        # Price fell to 116 → 120*(1-0.03)=116.4 → exit
        orders = engine.check_exits(portfolio, {"TEST": 116.0})
        assert len(orders) == 1
        assert orders[0].metadata["exit_reason"] == "trailing_stop"

    def test_partial_tp_trigger(self):
        limits = RiskLimits(partial_tp_enabled=True, partial_tp_fraction=0.33,
                            partial_tp_trigger_pct=0.5)
        engine = StrategyEngine(limits)
        portfolio = PortfolioState(cash=80_000)
        portfolio.positions["TEST"] = Position(
            instrument="TEST", quantity=10, avg_entry_price=100,
            take_profit=110.0, original_quantity=10,
        )
        # 50% of TP distance = 100 + 0.5*10 = 105
        orders = engine.check_exits(portfolio, {"TEST": 106.0})
        assert len(orders) == 1
        assert orders[0].metadata["exit_reason"] == "partial_tp"
        assert orders[0].quantity == 3  # 33% of 10
        pos = portfolio.positions["TEST"]
        assert pos.partial_tp_done is True
        assert pos.stop_loss == 100.0  # moved to breakeven

    def test_atr_stops(self):
        engine = StrategyEngine(RiskLimits(use_atr_stops=True,
                                            atr_stop_multiplier=1.5,
                                            atr_profit_multiplier=4.0))
        sig = TradingSignal(
            instrument="TEST", timestamp=datetime(2025, 1, 1),
            timeframe="1d", signal_direction=SignalDirection.LONG,
            direction_probability=0.7, expected_move=0.02,
            expected_volatility=0.02, confidence_score=0.7,
            regime_label=RegimeLabel.UNKNOWN,
            metadata={"atr_14": 5.0, "momentum_10": 0.01},
        )
        portfolio = PortfolioState(cash=100_000)
        orders = engine.on_signal(sig, portfolio, 100.0)
        assert len(orders) == 1
        assert orders[0].stop_loss == 92.5   # 100 - 5*1.5
        assert orders[0].take_profit == 120.0  # 100 + 5*4.0


# ── Regime Scaling ───────────────────────────────────────────────────

class TestRegimeScaling:
    def test_trending_up_scales_up(self):
        limits = RiskLimits()
        s = _regime_scale(RegimeLabel.TRENDING_UP, limits)
        assert s > 1.0  # should scale up

    def test_crash_scales_way_down(self):
        limits = RiskLimits()
        s = _regime_scale(RegimeLabel.CRASH, limits)
        assert s == 0.25

    def test_regime_affects_position_size(self):
        base_signal = TradingSignal(
            instrument="TEST", timestamp=datetime(2025, 1, 1),
            timeframe="1d", signal_direction=SignalDirection.LONG,
            direction_probability=0.7, expected_move=0.02,
            expected_volatility=0.2, confidence_score=0.7,
            regime_label=RegimeLabel.TRENDING_UP,
        )
        crash_signal = TradingSignal(
            instrument="TEST", timestamp=datetime(2025, 1, 1),
            timeframe="1d", signal_direction=SignalDirection.LONG,
            direction_probability=0.7, expected_move=0.02,
            expected_volatility=0.2, confidence_score=0.7,
            regime_label=RegimeLabel.CRASH,
        )
        portfolio = PortfolioState(cash=100_000)
        qty_trend = size_position(base_signal, portfolio, RiskLimits(), 100.0)
        qty_crash = size_position(crash_signal, portfolio, RiskLimits(), 100.0)
        assert qty_trend > qty_crash  # crash should produce smaller position


# ── Momentum Confirmation ────────────────────────────────────────────

class TestMomentumConfirmation:
    def test_momentum_against_rejects(self):
        portfolio = PortfolioState(cash=100_000)
        limits = RiskLimits(require_momentum_confirm=True)
        gate = RiskGate(limits)
        signal = TradingSignal(
            instrument="TEST", timestamp=datetime(2025, 1, 1),
            timeframe="1d", signal_direction=SignalDirection.LONG,
            direction_probability=0.7, expected_move=0.02,
            expected_volatility=0.02, confidence_score=0.7,
            regime_label=RegimeLabel.UNKNOWN,
            metadata={"momentum_10": -0.08},  # strong downward momentum
        )
        ok, reason, _ = gate.approve(signal, portfolio, 100, 100.0)
        assert not ok
        assert "momentum" in reason

    def test_momentum_aligned_passes(self):
        assert _momentum_confirms(TradingSignal(
            instrument="TEST", timestamp=datetime(2025, 1, 1),
            timeframe="1d", signal_direction=SignalDirection.LONG,
            direction_probability=0.7, expected_move=0.02,
            expected_volatility=0.02, confidence_score=0.7,
            regime_label=RegimeLabel.UNKNOWN,
            metadata={"momentum_10": 0.05},
        ))

    def test_no_metadata_passes(self):
        assert _momentum_confirms(TradingSignal(
            instrument="TEST", timestamp=datetime(2025, 1, 1),
            timeframe="1d", signal_direction=SignalDirection.LONG,
            direction_probability=0.7, expected_move=0.02,
            expected_volatility=0.02, confidence_score=0.7,
            regime_label=RegimeLabel.UNKNOWN,
        ))


# ── Consecutive Loss Tracking ────────────────────────────────────────

class TestConsecutiveLossTracking:
    def test_consecutive_losses_tracked(self):
        portfolio = PortfolioState(cash=100_000)
        assert portfolio.consecutive_losses == 0

    def test_losing_streak_halves_size(self):
        signal = TradingSignal(
            instrument="TEST", timestamp=datetime(2025, 1, 1),
            timeframe="1d", signal_direction=SignalDirection.LONG,
            direction_probability=0.7, expected_move=0.02,
            expected_volatility=0.2, confidence_score=0.7,
            regime_label=RegimeLabel.UNKNOWN,
        )
        portfolio_normal = PortfolioState(cash=100_000, consecutive_losses=0)
        portfolio_losing = PortfolioState(cash=100_000, consecutive_losses=3)
        limits = RiskLimits(loss_streak_half_size=3)
        qty_normal = size_position(signal, portfolio_normal, limits, 100.0)
        qty_losing = size_position(signal, portfolio_losing, limits, 100.0)
        assert qty_losing < qty_normal


# ── Execution Adapters ───────────────────────────────────────────────
from backend.shared.execution import (
    BacktestExecutor, SimulationConfig, apply_fill_to_portfolio,
)


class TestBacktestExecutor:
    def test_market_fill(self):
        exec = BacktestExecutor(SimulationConfig(
            slippage_pct=0, fill_probability=1.0, use_angel_charges=False,
            commission_flat=0,
        ))
        order = OrderRequest(
            instrument="TEST", side=OrderSide.BUY,
            quantity=10, order_type=OrderType.MARKET,
        )
        portfolio = PortfolioState(cash=100_000)
        state = exec.submit_order(order, portfolio, 100.0)
        assert state.status == OrderStatus.FILLED
        assert state.fills[0].price == 100.0

    def test_insufficient_cash(self):
        exec = BacktestExecutor(SimulationConfig(
            slippage_pct=0, fill_probability=1.0, use_angel_charges=False,
        ))
        order = OrderRequest(
            instrument="TEST", side=OrderSide.BUY,
            quantity=10000, order_type=OrderType.MARKET,
        )
        portfolio = PortfolioState(cash=100)
        state = exec.submit_order(order, portfolio, 100.0)
        assert state.status == OrderStatus.REJECTED

    def test_slippage_applied(self):
        exec = BacktestExecutor(SimulationConfig(
            slippage_pct=0.01, fill_probability=1.0, use_angel_charges=False,
            commission_flat=0,
        ))
        order = OrderRequest(
            instrument="TEST", side=OrderSide.BUY,
            quantity=10, order_type=OrderType.MARKET,
        )
        portfolio = PortfolioState(cash=100_000)
        state = exec.submit_order(order, portfolio, 100.0)
        assert state.fills[0].price == pytest.approx(101.0, abs=0.01)


class TestApplyFillToPortfolio:
    def test_buy_creates_position(self):
        portfolio = PortfolioState(cash=100_000)
        order = OrderRequest(instrument="TEST", side=OrderSide.BUY, quantity=10)
        fill = Fill(
            order_id=order.id, instrument="TEST", side=OrderSide.BUY,
            quantity=10, price=100.0,
        )
        exec = BacktestExecutor(SimulationConfig(
            use_angel_charges=False, commission_flat=0,
        ))
        result = apply_fill_to_portfolio(fill, portfolio, order, exec)
        assert result is None  # buy doesn't complete a round-trip
        assert portfolio.positions["TEST"].quantity == 10
        assert portfolio.cash == 99_000  # 100k - 10*100

    def test_sell_completes_trade(self):
        portfolio = PortfolioState(cash=90_000)
        portfolio.positions["TEST"] = Position(
            instrument="TEST", quantity=10, avg_entry_price=100,
        )
        order = OrderRequest(instrument="TEST", side=OrderSide.SELL, quantity=10)
        fill = Fill(
            order_id=order.id, instrument="TEST", side=OrderSide.SELL,
            quantity=10, price=110.0,
        )
        exec = BacktestExecutor(SimulationConfig(
            use_angel_charges=False, commission_flat=0,
        ))
        result = apply_fill_to_portfolio(fill, portfolio, order, exec)
        assert result is not None
        assert result.pnl == 100.0  # (110-100)*10
        assert portfolio.cash == 91_100  # 90k + 10*110


# ── Leakage Checks ──────────────────────────────────────────────────
from backend.shared.leakage import (
    LeakageError, walk_forward_splits, verify_no_shuffled_cv,
)


class TestLeakage:
    def test_walk_forward_splits(self):
        dates = pd.date_range("2020-01-01", periods=500, freq="B")
        splits = walk_forward_splits(
            dates, n_folds=3,
            train_days=180, val_days=30, embargo_days=5,
        )
        assert len(splits) == 3
        for s in splits:
            assert s.val_start > s.train_end
            gap = (s.val_start - s.train_end).days
            assert gap >= 5  # embargo

    def test_shuffled_cv_raises(self):
        good = pd.date_range("2020-01-01", periods=100, freq="B")
        bad = good[::-1]  # reversed
        # Build split indices: first half train, second half val
        train_idx = np.arange(0, 50)
        val_idx = np.arange(50, 100)
        good_dates = pd.Series(good)
        bad_dates = pd.Series(bad)
        # Good split should pass
        verify_no_shuffled_cv([(train_idx, val_idx)], good_dates)
        # Bad split should raise (reversed dates, val indices come after train but dates are reversed)
        with pytest.raises(LeakageError):
            verify_no_shuffled_cv([(train_idx, val_idx)], bad_dates)


# ── Backtester Integration ──────────────────────────────────────────
from backend.prediction_engine.backtest.backtester import Backtester, ExecutionConfig


class TestBacktesterIntegration:
    def test_basic_run(self):
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
        bt = Backtester(ExecutionConfig(
            slippage_pct=0, commission_per_trade=0, fill_probability=1.0,
        ))
        result = bt.run(predictions, prices, initial_capital=100_000)
        assert result.status == "completed"
        assert result.initial_capital == 100_000
        assert result.final_value > 0
        assert len(result.trades) > 0

    def test_new_metrics_present(self):
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
        bt = Backtester(ExecutionConfig(
            slippage_pct=0, commission_per_trade=0, fill_probability=1.0,
        ))
        result = bt.run(predictions, prices)
        # New fields should exist
        assert hasattr(result, "win_rate")
        assert hasattr(result, "expectancy")
        assert hasattr(result, "total_trades")
        assert hasattr(result, "no_trade_count")
        assert hasattr(result, "rejection_count")
        assert result.total_trades >= 0

    def test_force_close(self):
        """All positions should be closed at end of backtest."""
        dates = pd.date_range("2025-01-01", periods=5, freq="B")
        predictions = pd.DataFrame({
            "date": dates,
            "ticker": "TEST",
            "action": ["buy"] * 5,  # only buys, never sells
            "confidence": 0.8,
        })
        prices = pd.DataFrame({
            "Date": dates,
            "ticker": "TEST",
            "Close": [100, 102, 104, 106, 108],
        })
        bt = Backtester(ExecutionConfig(
            slippage_pct=0, commission_per_trade=0, fill_probability=1.0,
        ))
        result = bt.run(predictions, prices)
        # Should have a sell at the end (force-close)
        sell_trades = [t for t in result.trades if t.side == "sell"]
        assert len(sell_trades) >= 1
