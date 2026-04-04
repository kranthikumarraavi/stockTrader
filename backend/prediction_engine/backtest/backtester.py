# Backtesting logic

"""Walk-forward backtester using the shared strategy engine.

Uses the same ``StrategyEngine``, ``RiskGate``, and ``ExecutionAdapter``
as paper and live trading.  Only the data source (historical DataFrame)
and execution adapter (``BacktestExecutor``) differ.

This ensures backtest ↔ paper ↔ live parity.
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from backend.shared.schemas import (
    ExecutionMode,
    OrderSide,
    OrderStatus,
    PortfolioState,
    Position,
    RegimeLabel,
    RiskLimits,
    SignalDirection,
    TradeResult,
    TradingSignal,
)
from backend.shared.strategy_engine import StrategyEngine
from backend.shared.execution import (
    BacktestExecutor,
    SimulationConfig,
    apply_fill_to_portfolio,
)

logger = logging.getLogger(__name__)

STORAGE_DIR = Path(__file__).resolve().parents[3] / "storage" / "backtests"


# -----------------------------------------------------------------------
#  Legacy dataclasses kept for API / JSON compatibility
# -----------------------------------------------------------------------

@dataclass
class ExecutionConfig:
    """Configurable execution model for the backtester."""
    slippage_pct: float = 0.001
    fill_probability: float = 0.98
    use_angel_charges: bool = True
    trade_type: str = "intraday"
    commission_per_trade: float = 20.0


@dataclass
class Trade:
    """Single trade record for JSON serialisation."""
    date: str
    ticker: str
    side: str
    quantity: int
    price: float
    pnl: float = 0.0
    charges: float = 0.0
    exit_reason: str = ""


@dataclass
class BacktestResult:
    job_id: str
    status: str
    tickers: list[str]
    start_date: str
    end_date: str
    initial_capital: float
    final_value: float
    total_return_pct: float
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    max_drawdown_pct: float | None = None
    cagr_pct: float | None = None
    total_charges: float = 0.0
    win_rate: float | None = None
    avg_win: float | None = None
    avg_loss: float | None = None
    expectancy: float | None = None
    total_trades: int = 0
    no_trade_count: int = 0
    rejection_count: int = 0
    trades: list[Trade] = field(default_factory=list)
    completed_at: str | None = None


class Backtester:
    """Walk-forward backtester using the shared strategy engine.

    Uses the same strategy logic, risk checks, and execution simulation
    as paper and live trading.  Produces realistic results with
    proper slippage, charges, stop-loss / take-profit, and exit management.
    """

    def __init__(
        self,
        config: ExecutionConfig | None = None,
        risk_limits: RiskLimits | None = None,
    ) -> None:
        self.config = config or ExecutionConfig()
        self.risk_limits = risk_limits or RiskLimits()

        sim_config = SimulationConfig(
            slippage_pct=self.config.slippage_pct,
            fill_probability=self.config.fill_probability,
            use_angel_charges=self.config.use_angel_charges,
            trade_type=self.config.trade_type,
            commission_flat=self.config.commission_per_trade,
        )
        self.executor = BacktestExecutor(sim_config)
        self.strategy = StrategyEngine(self.risk_limits)

    @staticmethod
    def _infer_regime(
        adx: float, vol: float, rsi: float, dist_sma50: float,
    ) -> RegimeLabel:
        """Infer market regime from feature values.

        Simple rule-based regime detection using ADX (trend strength),
        volatility, RSI, and distance from SMA50.
        """
        if vol > 0.40:
            if rsi < 30:
                return RegimeLabel.CRASH
            return RegimeLabel.HIGH_VOLATILITY
        if adx > 25:
            if dist_sma50 > 0.02:
                return RegimeLabel.TRENDING_UP
            elif dist_sma50 < -0.02:
                return RegimeLabel.TRENDING_DOWN
        if vol < 0.12:
            return RegimeLabel.LOW_VOLATILITY
        return RegimeLabel.RANGE_BOUND

    def run(
        self,
        predictions_df: pd.DataFrame,
        price_df: pd.DataFrame,
        initial_capital: float = 100_000.0,
        job_id: str | None = None,
    ) -> BacktestResult:
        """Run a backtest using the shared strategy engine.

        Parameters
        ----------
        predictions_df : pd.DataFrame
            Must have columns: date, ticker, action, confidence.
        price_df : pd.DataFrame
            Must have columns: Date, ticker, Close.
        initial_capital : float
            Starting cash.
        job_id : str, optional
            Unique job identifier.
        """
        job_id = job_id or str(uuid.uuid4())

        # --- Initialise portfolio ---
        portfolio = PortfolioState(
            cash=initial_capital,
            execution_mode=ExecutionMode.BACKTEST,
        )

        trades: list[Trade] = []
        completed_trades: list[TradeResult] = []
        portfolio_values: list[float] = []
        no_trade_count = 0
        rejection_count = 0

        dates = sorted(predictions_df["date"].unique())

        for bar_idx, date in enumerate(dates):
            self.strategy.bar_index = bar_idx
            day_preds = predictions_df[predictions_df["date"] == date]
            day_prices = price_df[price_df["Date"] == date]

            # Build price dict for this day
            prices: dict[str, float] = {}
            for _, row in day_prices.iterrows():
                prices[row["ticker"]] = float(row["Close"])

            # Reset daily counters at start of each day
            portfolio.daily_pnl = 0.0
            portfolio.daily_trades = 0
            portfolio.daily_losses = 0

            # --- 1. Check exits on all open positions (SL / TP / trailing / max hold) ---
            exit_orders = self.strategy.check_exits(portfolio, prices)
            for order in exit_orders:
                price = prices.get(order.instrument, 0)
                if price <= 0:
                    continue
                state = self.executor.submit_order(order, portfolio, price, timestamp=date)
                if state.status == OrderStatus.FILLED:
                    fill = state.fills[0]
                    result = apply_fill_to_portfolio(
                        fill, portfolio, order, self.executor, bar_idx,
                    )
                    trades.append(Trade(
                        date=str(date)[:10],
                        ticker=order.instrument,
                        side="sell",
                        quantity=fill.quantity,
                        price=round(fill.price, 2),
                        pnl=round(result.pnl, 2) if result else 0.0,
                        charges=round(result.charges, 2) if result else 0.0,
                        exit_reason=order.metadata.get("exit_reason", ""),
                    ))
                    if result:
                        completed_trades.append(result)

            # --- 2. Process model signals ---
            for _, pred in day_preds.iterrows():
                ticker = pred["ticker"]
                action = pred["action"]
                confidence = pred.get("confidence", 0.5)
                price = prices.get(ticker)
                if price is None or price <= 0:
                    continue

                # Convert prediction to TradingSignal
                if action == "buy":
                    direction = SignalDirection.LONG
                elif action == "sell":
                    direction = SignalDirection.SHORT
                else:
                    direction = SignalDirection.FLAT

                # Extract real feature values (passed through from router)
                vol = float(pred.get("volatility_20", 0.20)) or 0.20
                atr = float(pred.get("atr_14", 0.0)) or 0.0
                momentum = float(pred.get("momentum_10", 0.0)) or 0.0
                ema_cross = float(pred.get("ema_crossover", 0.0)) or 0.0
                adx = float(pred.get("adx_14", 0.0)) or 0.0
                rsi = float(pred.get("rsi_14", 50.0)) or 50.0
                dist_sma50 = float(pred.get("distance_sma50", 0.0)) or 0.0

                # Infer regime from feature values
                regime = self._infer_regime(adx, vol, rsi, dist_sma50)

                signal = TradingSignal(
                    instrument=ticker,
                    timestamp=pd.Timestamp(date).to_pydatetime(),
                    timeframe="1d",
                    signal_direction=direction,
                    direction_probability=max(confidence, 1 - confidence),
                    expected_move=(confidence - 0.5) * vol * 2,
                    expected_volatility=vol,
                    confidence_score=confidence,
                    regime_label=regime,
                    no_trade_flag=(action == "hold"),
                    model_version="backtest",
                    metadata={
                        "atr_14": atr,
                        "momentum_10": momentum,
                        "ema_crossover": ema_cross,
                        "adx_14": adx,
                        "rsi_14": rsi,
                    },
                )

                if signal.no_trade_flag:
                    no_trade_count += 1
                    continue

                # Get orders from shared strategy engine
                orders = self.strategy.on_signal(signal, portfolio, price)
                if not orders:
                    if signal.signal_direction != SignalDirection.FLAT:
                        rejection_count += 1
                    continue

                for order in orders:
                    state = self.executor.submit_order(
                        order, portfolio, price, timestamp=date,
                    )
                    if state.status == OrderStatus.FILLED:
                        fill = state.fills[0]
                        result = apply_fill_to_portfolio(
                            fill, portfolio, order, self.executor, bar_idx,
                        )
                        trades.append(Trade(
                            date=str(date)[:10],
                            ticker=order.instrument,
                            side=order.side.value,
                            quantity=fill.quantity,
                            price=round(fill.price, 2),
                            pnl=round(result.pnl, 2) if result else 0.0,
                            charges=round(result.charges, 2) if result else 0.0,
                        ))
                        if result:
                            completed_trades.append(result)
                    elif state.status == OrderStatus.REJECTED:
                        rejection_count += 1

            # --- 3. Mark-to-market ---
            for instrument, pos in portfolio.positions.items():
                if pos.is_open and instrument in prices:
                    pos.mark_to_market(prices[instrument])
            portfolio_values.append(portfolio.equity)

        # --- 4. Force-close all remaining positions at last day's prices ---
        if dates:
            last_prices_df = price_df[price_df["Date"] == dates[-1]]
            last_prices = {
                row["ticker"]: float(row["Close"])
                for _, row in last_prices_df.iterrows()
            }
            for instrument in list(portfolio.positions.keys()):
                pos = portfolio.positions[instrument]
                if not pos.is_open or pos.quantity <= 0:
                    continue
                price = last_prices.get(instrument)
                if price is None:
                    continue

                order = self.strategy._make_exit_order(pos, price, "end_of_backtest")
                state = self.executor.submit_order(
                    order, portfolio, price, timestamp=dates[-1],
                )
                if state.status == OrderStatus.FILLED:
                    fill = state.fills[0]
                    result = apply_fill_to_portfolio(
                        fill, portfolio, order, self.executor, bar_idx + 1,
                    )
                    trades.append(Trade(
                        date=str(dates[-1])[:10],
                        ticker=instrument,
                        side="sell",
                        quantity=fill.quantity,
                        price=round(fill.price, 2),
                        pnl=round(result.pnl, 2) if result else 0.0,
                        charges=round(result.charges, 2) if result else 0.0,
                        exit_reason="end_of_backtest",
                    ))
                    if result:
                        completed_trades.append(result)

        # --- 5. Compute metrics ---
        final_value = portfolio.equity
        total_return = (final_value / initial_capital - 1) * 100

        sharpe = self._sharpe(portfolio_values)
        sortino = self._sortino(portfolio_values)
        max_dd = self._max_drawdown(portfolio_values)
        cagr = self._cagr(initial_capital, final_value, len(dates))

        # Trade-level metrics
        pnls = [t.pnl for t in completed_trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        win_rate = len(wins) / len(pnls) * 100 if pnls else None
        avg_win = sum(wins) / len(wins) if wins else None
        avg_loss = sum(losses) / len(losses) if losses else None
        expectancy = sum(pnls) / len(pnls) if pnls else None

        result = BacktestResult(
            job_id=job_id,
            status="completed",
            tickers=sorted(set(predictions_df["ticker"])),
            start_date=str(dates[0])[:10] if dates else "",
            end_date=str(dates[-1])[:10] if dates else "",
            initial_capital=initial_capital,
            final_value=round(final_value, 2),
            total_return_pct=round(total_return, 2),
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown_pct=max_dd,
            cagr_pct=cagr,
            total_charges=round(portfolio.total_commission, 2),
            win_rate=round(win_rate, 2) if win_rate is not None else None,
            avg_win=round(avg_win, 2) if avg_win is not None else None,
            avg_loss=round(avg_loss, 2) if avg_loss is not None else None,
            expectancy=round(expectancy, 2) if expectancy is not None else None,
            total_trades=len(completed_trades),
            no_trade_count=no_trade_count,
            rejection_count=rejection_count,
            trades=trades,
            completed_at=datetime.now(timezone.utc).isoformat() + "Z",
        )

        self._save_result(result)
        return result

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    @staticmethod
    def _sharpe(values: list[float], risk_free: float = 0.0) -> float | None:
        if len(values) < 2:
            return None
        rets = pd.Series(values).pct_change().dropna()
        if rets.std() == 0:
            return None
        return round(float((rets.mean() - risk_free) / rets.std() * math.sqrt(252)), 4)

    @staticmethod
    def _sortino(values: list[float], risk_free: float = 0.0) -> float | None:
        if len(values) < 2:
            return None
        rets = pd.Series(values).pct_change().dropna()
        down = rets[rets < 0]
        if down.empty or down.std() == 0:
            return None
        return round(float((rets.mean() - risk_free) / down.std() * math.sqrt(252)), 4)

    @staticmethod
    def _max_drawdown(values: list[float]) -> float | None:
        if len(values) < 2:
            return None
        peak = values[0]
        max_dd = 0.0
        for v in values:
            if v > peak:
                peak = v
            dd = (peak - v) / peak
            if dd > max_dd:
                max_dd = dd
        return round(max_dd * 100, 2)

    @staticmethod
    def _cagr(initial: float, final: float, days: int) -> float | None:
        if days <= 0 or initial <= 0:
            return None
        years = days / 252  # trading days
        if years <= 0:
            return None
        return round(((final / initial) ** (1 / years) - 1) * 100, 2)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    @staticmethod
    def _save_result(result: BacktestResult) -> Path:
        job_dir = STORAGE_DIR / result.job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        path = job_dir / "results.json"
        path.write_text(json.dumps(asdict(result), indent=2, default=str))
        logger.info("Backtest results saved â†’ %s", path)
        return path

    @staticmethod
    def load_result(job_id: str) -> dict | None:
        path = STORAGE_DIR / job_id / "results.json"
        if path.exists():
            return json.loads(path.read_text())
        return None

