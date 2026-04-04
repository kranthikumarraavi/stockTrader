"""Shared execution adapter abstraction.

Defines the ``ExecutionAdapter`` protocol and three implementations:
- ``BacktestExecutor`` — deterministic fill simulator for backtests
- ``PaperExecutor`` — realistic fill simulator for paper trading
- ``LiveExecutor`` — delegates to the broker adapter (Angel One)

All adapters consume ``OrderRequest`` and produce ``Fill`` events,
ensuring identical order lifecycle semantics across modes.
"""

from __future__ import annotations

import logging
import math
import random
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Protocol

from backend.shared.schemas import (
    ExecutionMode,
    Fill,
    OrderRequest,
    OrderSide,
    OrderState,
    OrderStatus,
    PortfolioState,
    Position,
    TradeResult,
)

logger = logging.getLogger(__name__)


# =====================================================================
#  Execution config (shared simulation parameters)
# =====================================================================

class SimulationConfig:
    """Parameters for fill simulation.  Used by both paper and backtest."""

    def __init__(
        self,
        slippage_pct: float = 0.001,
        fill_probability: float = 0.98,
        latency_ms: int = 50,
        use_angel_charges: bool = True,
        trade_type: str = "intraday",
        partial_fill_prob: float = 0.0,     # 0 = no partial fills
        commission_flat: float = 20.0,       # only used when angel charges off
    ):
        self.slippage_pct = slippage_pct
        self.fill_probability = fill_probability
        self.latency_ms = latency_ms
        self.use_angel_charges = use_angel_charges
        self.trade_type = trade_type
        self.partial_fill_prob = partial_fill_prob
        self.commission_flat = commission_flat


# =====================================================================
#  Abstract adapter
# =====================================================================

class ExecutionAdapter(ABC):
    """Protocol that every execution mode must implement."""

    @abstractmethod
    def submit_order(
        self,
        order: OrderRequest,
        portfolio: PortfolioState,
        market_price: float,
        timestamp: datetime | None = None,
    ) -> OrderState:
        """Submit an order and return its resulting state.

        For backtest/paper this fills (or rejects) synchronously.
        For live this submits to the broker and returns OPEN status.
        """
        ...

    @abstractmethod
    def get_commission(
        self, buy_price: float, sell_price: float, qty: int,
    ) -> float:
        """Calculate round-trip commission/charges."""
        ...


# =====================================================================
#  Backtest executor
# =====================================================================

class BacktestExecutor(ExecutionAdapter):
    """Deterministic fill simulator for backtesting.

    Applies configurable slippage and realistic Angel One charges.
    Fills are synchronous (no partial fills by default).
    """

    def __init__(self, config: SimulationConfig | None = None) -> None:
        self.config = config or SimulationConfig()
        self._charge_calc = None

    def submit_order(
        self,
        order: OrderRequest,
        portfolio: PortfolioState,
        market_price: float,
        timestamp: datetime | None = None,
    ) -> OrderState:
        ts = timestamp or datetime.now(timezone.utc)
        state = OrderState(request=order, status=OrderStatus.PENDING, updated_at=ts)

        # Fill probability check
        if random.random() > self.config.fill_probability:
            state.status = OrderStatus.REJECTED
            state.reject_reason = "fill_probability_miss"
            return state

        # Apply slippage
        if order.side == OrderSide.BUY:
            exec_price = market_price * (1 + self.config.slippage_pct)
        else:
            exec_price = market_price * (1 - self.config.slippage_pct)
        exec_price = round(exec_price, 2)

        # Check cash for buys
        if order.side == OrderSide.BUY:
            cost = order.quantity * exec_price
            if cost > portfolio.cash:
                state.status = OrderStatus.REJECTED
                state.reject_reason = "insufficient_cash"
                return state

        slippage = abs(exec_price - market_price)

        fill = Fill(
            order_id=order.id,
            instrument=order.instrument,
            side=order.side,
            quantity=order.quantity,
            price=exec_price,
            commission=0.0,  # calculated at trade close
            slippage=slippage,
            timestamp=ts,
        )
        state.apply_fill(fill)
        return state

    def get_commission(
        self, buy_price: float, sell_price: float, qty: int,
    ) -> float:
        if self.config.use_angel_charges:
            try:
                if self._charge_calc is None:
                    from backend.services.brokerage_calculator import (
                        calculate_charges,
                        TradeType,
                    )
                    self._charge_calc = (calculate_charges, TradeType)
                calc, TT = self._charge_calc
                tt = TT.DELIVERY if self.config.trade_type == "delivery" else TT.INTRADAY
                result = calc(buy_price, sell_price, qty, tt)
                return result.total_charges
            except ImportError:
                pass
        return self.config.commission_flat * 2


# =====================================================================
#  Paper executor
# =====================================================================

class PaperExecutor(ExecutionAdapter):
    """Fill simulator for paper trading.

    Behaves like ``BacktestExecutor`` but adds randomised latency
    and optional partial fills to better mimic live conditions.
    """

    def __init__(self, config: SimulationConfig | None = None) -> None:
        self.config = config or SimulationConfig(
            partial_fill_prob=0.05,   # 5% chance of partial fills in paper
        )
        self._bt_executor = BacktestExecutor(self.config)

    def submit_order(
        self,
        order: OrderRequest,
        portfolio: PortfolioState,
        market_price: float,
        timestamp: datetime | None = None,
    ) -> OrderState:
        # Delegate to backtest executor for fill logic
        state = self._bt_executor.submit_order(order, portfolio, market_price, timestamp)

        # Simulate partial fill
        if (state.status == OrderStatus.FILLED
                and self.config.partial_fill_prob > 0
                and random.random() < self.config.partial_fill_prob
                and order.quantity > 1):
            partial_qty = max(1, int(order.quantity * random.uniform(0.3, 0.9)))
            state.filled_qty = partial_qty
            state.fills[0].quantity = partial_qty
            state.status = OrderStatus.PARTIAL

        return state

    def get_commission(
        self, buy_price: float, sell_price: float, qty: int,
    ) -> float:
        return self._bt_executor.get_commission(buy_price, sell_price, qty)


# =====================================================================
#  Live executor (stub — delegates to angel_adapter)
# =====================================================================

class LiveExecutor(ExecutionAdapter):
    """Delegates to the real broker adapter.

    This is a thin wrapper provided for interface parity.  The actual
    broker communication happens in ``trading_engine.angel_adapter``.
    """

    def __init__(self) -> None:
        self._adapter = None

    def _get_adapter(self):
        if self._adapter is None:
            from backend.trading_engine.angel_adapter import get_adapter
            self._adapter = get_adapter()
        return self._adapter

    def submit_order(
        self,
        order: OrderRequest,
        portfolio: PortfolioState,
        market_price: float,
        timestamp: datetime | None = None,
    ) -> OrderState:
        adapter = self._get_adapter()
        ts = timestamp or datetime.now(timezone.utc)
        state = OrderState(request=order, status=OrderStatus.OPEN, updated_at=ts)

        try:
            broker_id = adapter.place_order(
                symbol=order.instrument,
                side=order.side.value.upper(),
                qty=order.quantity,
                order_type=order.order_type.value.upper(),
                price=order.limit_price,
            )
            state.broker_order_id = broker_id
        except Exception as exc:
            state.status = OrderStatus.REJECTED
            state.reject_reason = str(exc)
            logger.error("Broker reject %s: %s", order.instrument, exc)

        return state

    def get_commission(
        self, buy_price: float, sell_price: float, qty: int,
    ) -> float:
        try:
            from backend.services.brokerage_calculator import (
                calculate_charges,
                TradeType,
            )
            result = calculate_charges(buy_price, sell_price, qty, TradeType.INTRADAY)
            return result.total_charges
        except ImportError:
            return 40.0  # fallback


# =====================================================================
#  Portfolio updater — applies fills to portfolio state
# =====================================================================

def apply_fill_to_portfolio(
    fill: Fill,
    portfolio: PortfolioState,
    order: OrderRequest,
    executor: ExecutionAdapter,
    bar_index: int = 0,
) -> TradeResult | None:
    """Apply a fill to the portfolio and return a ``TradeResult`` if a
    round-trip trade was completed (i.e., position closed).

    This function is used identically by all three execution modes.
    """
    instrument = fill.instrument
    pos = portfolio.positions.get(instrument)

    if fill.side == OrderSide.BUY:
        if pos is None or not pos.is_open:
            # New position
            atr = order.metadata.get("atr_at_entry", 0.0) if order.metadata else 0.0
            pos = Position(
                instrument=instrument,
                quantity=fill.quantity,
                avg_entry_price=fill.price,
                stop_loss=order.stop_loss,
                take_profit=order.take_profit,
                trailing_stop_pct=order.trailing_stop_pct,
                trailing_high=fill.price,
                entry_time=fill.timestamp,
                entry_bar_index=bar_index,
                original_quantity=fill.quantity,
                atr_at_entry=atr,
            )
            portfolio.positions[instrument] = pos
        else:
            # Add to existing (shouldn't happen with no-pyramid rule)
            total_value = pos.avg_entry_price * pos.quantity + fill.price * fill.quantity
            pos.quantity += fill.quantity
            pos.avg_entry_price = total_value / pos.quantity
        portfolio.cash -= fill.quantity * fill.price
        portfolio.daily_trades += 1
        return None

    elif fill.side == OrderSide.SELL:
        if pos is None or pos.quantity <= 0:
            logger.warning("Sell fill for %s but no open position.", instrument)
            return None

        entry_price = pos.avg_entry_price
        exit_price = fill.price
        qty = min(fill.quantity, pos.quantity)
        charges = executor.get_commission(entry_price, exit_price, qty)
        pnl = (exit_price - entry_price) * qty - charges
        slippage = fill.slippage * qty

        pos.realised_pnl += pnl
        pos.total_charges += charges
        pos.quantity -= qty

        portfolio.cash += qty * exit_price - charges
        portfolio.daily_pnl += pnl
        portfolio.total_commission += charges
        portfolio.daily_trades += 1
        if pnl < 0:
            portfolio.daily_losses += 1
            portfolio.consecutive_losses += 1
        else:
            portfolio.consecutive_losses = 0

        if pos.quantity <= 0:
            portfolio.positions[instrument] = Position(instrument=instrument)

        exit_reason = order.metadata.get("exit_reason", "signal")

        return TradeResult(
            instrument=instrument,
            side="long",
            entry_price=round(entry_price, 2),
            exit_price=round(exit_price, 2),
            quantity=qty,
            pnl=round(pnl, 2),
            charges=round(charges, 2),
            slippage=round(slippage, 4),
            holding_bars=bar_index - pos.entry_bar_index,
            entry_time=pos.entry_time,
            exit_time=fill.timestamp,
            exit_reason=exit_reason,
            signal_confidence=order.signal.confidence_score if order.signal else 0.0,
            regime_at_entry=order.signal.regime_label.value if order.signal else "",
            execution_mode=portfolio.execution_mode.value,
        )

    return None
