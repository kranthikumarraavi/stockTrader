"""Shared strategy engine — converts signals into order decisions.

This module is the single source of truth for strategy logic.  It is
consumed identically by live trading, paper trading, and backtesting.
Only the *execution adapter* that fills the resulting ``OrderRequest``
differs between modes.

Strategy improvements:
- ATR-based adaptive stops (volatility-scaled SL/TP)
- Trailing stop enabled by default (4%)
- Regime-aware position sizing (scale up in trends, cut in crashes)
- Momentum confirmation filter (skip counter-trend entries)
- Partial profit booking (scale out 50% at 60% of TP target)
- Graduated losing-streak response (half size after 3 losses)
"""

from __future__ import annotations

import logging
import math
from datetime import datetime

from backend.shared.schemas import (
    Fill,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    PortfolioState,
    Position,
    RegimeLabel,
    RiskLimits,
    SignalDirection,
    TradeResult,
    TradingSignal,
)

logger = logging.getLogger(__name__)


# =====================================================================
#  Regime-based scaling factor
# =====================================================================

def _regime_scale(regime: RegimeLabel, limits: RiskLimits) -> float:
    """Return a multiplier [0.25 .. 1.2] based on the current regime."""
    _MAP = {
        RegimeLabel.TRENDING_UP: limits.regime_scale_trending,
        RegimeLabel.TRENDING_DOWN: limits.regime_scale_range,   # cautious in downtrend
        RegimeLabel.RANGE_BOUND: limits.regime_scale_range,
        RegimeLabel.HIGH_VOLATILITY: limits.regime_scale_high_vol,
        RegimeLabel.LOW_VOLATILITY: 1.0,
        RegimeLabel.BREAKOUT: 1.0,
        RegimeLabel.CRASH: limits.regime_scale_crash,
        RegimeLabel.UNKNOWN: 1.0,
    }
    return _MAP.get(regime, 1.0)


# =====================================================================
#  Momentum confirmation
# =====================================================================

def _momentum_confirms(signal: TradingSignal) -> bool:
    """Check that momentum direction aligns with the signal.

    Uses metadata keys ``momentum_10`` and ``ema_crossover`` that the
    backtester / signal generator should populate from feature data.
    Returns True if momentum data is unavailable (fail-open).
    """
    meta = signal.metadata
    if not meta:
        return True

    momentum = meta.get("momentum_10")
    ema_cross = meta.get("ema_crossover")

    if signal.signal_direction == SignalDirection.LONG:
        # Reject LONG if momentum is strongly negative
        if momentum is not None and momentum < -0.05:
            return False
        if ema_cross is not None and ema_cross < -0.8:
            return False
    elif signal.signal_direction == SignalDirection.SHORT:
        # Reject SHORT-exit if momentum is strongly positive
        if momentum is not None and momentum > 0.05:
            return False

    return True


# =====================================================================
#  Risk gate — pre-trade validation
# =====================================================================

class RiskGate:
    """Stateless risk checks applied before every order.

    Every execution mode calls the same ``approve()`` method.
    """

    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits()

    def approve(
        self,
        signal: TradingSignal,
        portfolio: PortfolioState,
        proposed_qty: int,
        proposed_price: float,
    ) -> tuple[bool, str, int]:
        """Validate and optionally reduce quantity.

        Returns
        -------
        (approved, reason, adjusted_qty)
        """
        lim = self.limits

        # 1. Kill switch: daily loss exceeded
        if portfolio.equity > 0:
            daily_loss_pct = abs(min(portfolio.daily_pnl, 0)) / portfolio.equity
            if daily_loss_pct >= lim.max_daily_loss_pct:
                return False, "daily_loss_limit", 0

        # 2. No-trade flag
        if signal.no_trade_flag:
            return False, "no_trade_flag", 0

        # 3. Confidence threshold
        if signal.confidence_score < lim.min_signal_confidence:
            return False, f"low_confidence={signal.confidence_score:.2f}", 0

        # 4. Event risk
        if signal.event_risk_score > lim.max_event_risk:
            return False, f"high_event_risk={signal.event_risk_score:.2f}", 0

        # 5. Max positions
        if (signal.signal_direction != SignalDirection.FLAT
                and portfolio.open_position_count >= lim.max_positions):
            return False, "max_positions_reached", 0

        # 6. Duplicate / already holding
        existing = portfolio.positions.get(signal.instrument)
        if signal.signal_direction == SignalDirection.LONG and existing and existing.quantity > 0:
            return False, "already_long", 0

        # 7. Momentum confirmation (new)
        if lim.require_momentum_confirm and not _momentum_confirms(signal):
            return False, "momentum_against", 0

        # 8. Exposure limit
        equity = max(portfolio.equity, 1.0)
        proposed_value = proposed_qty * proposed_price
        max_per_pos = equity * lim.max_position_pct
        if proposed_value > max_per_pos:
            proposed_qty = max(1, int(max_per_pos / proposed_price))
            proposed_value = proposed_qty * proposed_price

        new_gross = portfolio.gross_exposure + proposed_value
        if new_gross > equity * lim.max_gross_exposure_pct:
            room = equity * lim.max_gross_exposure_pct - portfolio.gross_exposure
            if room <= 0:
                return False, "gross_exposure_limit", 0
            proposed_qty = max(1, int(room / proposed_price))

        # 9. Loss streak cooldown (hard)
        if portfolio.daily_losses >= lim.max_loss_streak_trades:
            return False, "loss_streak_cooldown", 0

        # 10. Volatility circuit breaker
        if signal.expected_volatility > lim.volatility_circuit_breaker:
            return False, f"vol_circuit_breaker={signal.expected_volatility:.3f}", 0

        return True, "approved", proposed_qty


# =====================================================================
#  Position sizer (regime-aware + graduated loss response)
# =====================================================================

def size_position(
    signal: TradingSignal,
    portfolio: PortfolioState,
    limits: RiskLimits,
    current_price: float,
) -> int:
    """Calculate position size. Factors in:

    1. Confidence ramp (30% at threshold → 100% at full)
    2. Volatility inverse scaling
    3. Regime-based multiplier
    4. Graduated loss-streak reduction
    """
    equity = max(portfolio.equity, 1.0)
    max_alloc = equity * limits.max_position_pct  # e.g. 20% of equity

    # --- 1. Confidence ramp: 30% at threshold, 100% at full confidence ---
    min_conf = limits.min_signal_confidence
    excess = max(signal.confidence_score - min_conf, 0.0)
    max_excess = 1.0 - min_conf
    conf_scale = min(0.3 + 0.7 * (excess / max_excess), 1.0)

    # --- 2. Volatility adjustment (reduce in high vol, floor 40%) ---
    vol_adj = 1.0
    if signal.expected_volatility > 0.01:
        vol_adj = max(0.4, min(1.0, 0.25 / signal.expected_volatility))

    # --- 3. Regime-based scaling ---
    regime_adj = _regime_scale(signal.regime_label, limits)

    # --- 4. Graduated losing-streak response ---
    loss_adj = 1.0
    if portfolio.consecutive_losses >= limits.loss_streak_half_size:
        loss_adj = 0.5  # half size after N consecutive losses

    # --- 5. Allocate ---
    alloc = max_alloc * conf_scale * vol_adj * regime_adj * loss_adj
    alloc = min(alloc, max_alloc)

    # Keep 5% cash buffer
    available = portfolio.cash * 0.95
    alloc = min(alloc, available)

    if current_price <= 0:
        return 0
    qty = max(1, int(alloc / current_price))
    return qty


# =====================================================================
#  ATR-based adaptive stops
# =====================================================================

def _compute_stops(
    current_price: float,
    signal: TradingSignal,
    limits: RiskLimits,
) -> tuple[float, float, float]:
    """Return (stop_loss, take_profit, atr_at_entry).

    Prefers ATR-based stops when signal metadata contains ``atr_14``.
    Falls back to fixed-percentage stops otherwise.
    """
    atr = signal.metadata.get("atr_14", 0.0) if signal.metadata else 0.0

    if limits.use_atr_stops and atr > 0:
        stop_loss = round(current_price - atr * limits.atr_stop_multiplier, 2)
        take_profit = round(current_price + atr * limits.atr_profit_multiplier, 2)
    else:
        stop_loss = round(current_price * (1 - limits.stop_loss_pct), 2)
        take_profit = round(current_price * (1 + limits.take_profit_pct), 2)
        atr = 0.0

    # Safety: ensure SL is reasonable (at least 1% away)
    min_sl = round(current_price * 0.99, 2)
    if stop_loss > min_sl:
        stop_loss = min_sl

    return stop_loss, take_profit, atr


# =====================================================================
#  Strategy engine — the single entry point
# =====================================================================

class StrategyEngine:
    """Converts ``TradingSignal`` → ``list[OrderRequest]``.

    This class is used identically by live, paper, and backtest.
    It calls the shared risk gate, position sizer, and exit logic.

    Improvements over v1:
    - ATR-based adaptive stops
    - Trailing stop default 4%
    - Partial profit booking at 60% of TP target
    - Regime-aware sizing
    - Momentum confirmation
    """

    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits()
        self.risk_gate = RiskGate(self.limits)
        self._bar_index = 0  # incremented externally for backtests

    @property
    def bar_index(self) -> int:
        return self._bar_index

    @bar_index.setter
    def bar_index(self, value: int) -> None:
        self._bar_index = value

    # ----------------------------------------------------------------
    #  Entry signals
    # ----------------------------------------------------------------

    def on_signal(
        self,
        signal: TradingSignal,
        portfolio: PortfolioState,
        current_price: float,
    ) -> list[OrderRequest]:
        """Process one prediction signal and return zero or more orders."""
        orders: list[OrderRequest] = []

        if signal.signal_direction == SignalDirection.FLAT:
            pos = portfolio.positions.get(signal.instrument)
            if pos and pos.is_open:
                orders.append(self._make_exit_order(
                    pos, current_price, reason="signal_flat",
                ))
            return orders

        if signal.signal_direction == SignalDirection.LONG:
            qty = size_position(signal, portfolio, self.limits, current_price)
            approved, reason, adj_qty = self.risk_gate.approve(
                signal, portfolio, qty, current_price,
            )
            if not approved:
                logger.debug("Signal rejected for %s: %s", signal.instrument, reason)
                return orders

            stop_loss, take_profit, atr = _compute_stops(
                current_price, signal, self.limits,
            )

            orders.append(OrderRequest(
                instrument=signal.instrument,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=adj_qty,
                stop_loss=stop_loss,
                take_profit=take_profit,
                trailing_stop_pct=self.limits.trailing_stop_pct,
                signal=signal,
                metadata={"atr_at_entry": atr},
            ))

        elif signal.signal_direction == SignalDirection.SHORT:
            pos = portfolio.positions.get(signal.instrument)
            if pos and pos.quantity > 0:
                orders.append(self._make_exit_order(
                    pos, current_price, reason="signal_short",
                ))

        return orders

    # ----------------------------------------------------------------
    #  Exit logic (SL / TP / trailing / partial TP / max-hold)
    # ----------------------------------------------------------------

    def check_exits(
        self,
        portfolio: PortfolioState,
        prices: dict[str, float],
    ) -> list[OrderRequest]:
        """Check all open positions for exit conditions.

        Called every bar / tick in every execution mode.
        Includes partial profit-taking when enabled.
        """
        orders: list[OrderRequest] = []

        for instrument, pos in list(portfolio.positions.items()):
            if not pos.is_open or pos.quantity <= 0:
                continue

            price = prices.get(instrument)
            if price is None:
                continue

            pos.mark_to_market(price)

            # --- Partial profit booking ---
            partial_order = self._check_partial_tp(pos, price)
            if partial_order:
                orders.append(partial_order)
                continue  # don't also full-exit this bar

            reason = self._should_exit(pos, price)
            if reason:
                orders.append(self._make_exit_order(pos, price, reason))

        return orders

    def _check_partial_tp(
        self, pos: Position, price: float,
    ) -> OrderRequest | None:
        """If partial TP is enabled and price reached the trigger, sell half."""
        lim = self.limits
        if not lim.partial_tp_enabled or pos.partial_tp_done:
            return None
        if pos.original_quantity < 2:
            return None
        if pos.take_profit is None:
            return None

        tp_distance = pos.take_profit - pos.avg_entry_price
        if tp_distance <= 0:
            return None

        trigger_price = pos.avg_entry_price + tp_distance * lim.partial_tp_trigger_pct
        if price >= trigger_price:
            sell_qty = max(1, int(pos.original_quantity * lim.partial_tp_fraction))
            sell_qty = min(sell_qty, pos.quantity)  # don't sell more than we hold
            if sell_qty <= 0:
                return None

            # Move SL to breakeven after partial exit
            pos.stop_loss = pos.avg_entry_price
            pos.partial_tp_done = True

            return OrderRequest(
                instrument=pos.instrument,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=sell_qty,
                metadata={"exit_reason": "partial_tp"},
            )

        return None

    def _should_exit(self, pos: Position, price: float) -> str | None:
        """Return exit reason or None if position should stay open."""
        # Stop loss
        if pos.stop_loss and price <= pos.stop_loss:
            return "stop_loss"

        # Take profit (full)
        if pos.take_profit and price >= pos.take_profit:
            return "take_profit"

        # Trailing stop
        if pos.trailing_stop_pct and pos.trailing_high > 0:
            trail_price = pos.trailing_high * (1 - pos.trailing_stop_pct)
            if price <= trail_price:
                return "trailing_stop"

        # Max holding period
        bars_held = self._bar_index - pos.entry_bar_index
        if bars_held >= self.limits.max_holding_bars:
            return "max_holding"

        return None

    def _make_exit_order(
        self, pos: Position, price: float, reason: str,
    ) -> OrderRequest:
        return OrderRequest(
            instrument=pos.instrument,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=abs(pos.quantity),
            metadata={"exit_reason": reason},
        )
