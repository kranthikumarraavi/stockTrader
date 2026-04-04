"""Shared signal, order, position, and risk schemas.

These are the canonical data types consumed by the strategy engine,
execution adapters (live / paper / backtest), and risk rules.  All
three execution modes must use the same schemas.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# =====================================================================
#  Enums
# =====================================================================

class SignalDirection(str, enum.Enum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"         # close position / no trade


class OrderSide(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, enum.Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    OPEN = "open"             # submitted to broker / simulator
    PARTIAL = "partial"       # partially filled
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class RegimeLabel(str, enum.Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGE_BOUND = "range_bound"
    HIGH_VOLATILITY = "high_vol"
    LOW_VOLATILITY = "low_vol"
    BREAKOUT = "breakout"
    CRASH = "crash"
    UNKNOWN = "unknown"


class ExecutionMode(str, enum.Enum):
    LIVE = "live"
    PAPER = "paper"
    BACKTEST = "backtest"


# =====================================================================
#  Trading Signal (output of prediction engine)
# =====================================================================

@dataclass
class TradingSignal:
    """Unified signal emitted by the prediction engine.

    Every execution mode (live, paper, backtest) receives exactly this
    schema.  The strategy engine converts it into an ``OrderRequest``.
    """
    instrument: str
    timestamp: datetime
    timeframe: str                           # e.g. "1d", "1h"
    signal_direction: SignalDirection
    direction_probability: float             # calibrated P(direction)
    expected_move: float                     # expected % move
    expected_volatility: float               # annualised vol estimate
    confidence_score: float                  # 0-1, trades below threshold are skipped
    regime_label: RegimeLabel
    event_risk_score: float = 0.0            # 0-1, high = risky event window
    sentiment_score: float = 0.0             # -1 to +1
    no_trade_flag: bool = False              # True = abstain
    model_version: str = ""
    top_features: list[tuple[str, float]] = field(default_factory=list)
    recommended_holding_horizon: int = 1     # bars
    metadata: dict[str, Any] = field(default_factory=dict)


# =====================================================================
#  Order lifecycle
# =====================================================================

@dataclass
class OrderRequest:
    """Created by the strategy / trading engine.  Immutable once submitted."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    instrument: str = ""
    side: OrderSide = OrderSide.BUY
    order_type: OrderType = OrderType.MARKET
    quantity: int = 0
    limit_price: float | None = None
    stop_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    trailing_stop_pct: float | None = None
    time_in_force: str = "DAY"               # DAY, GTC, IOC
    idempotency_key: str = field(default_factory=lambda: str(uuid.uuid4()))
    signal: TradingSignal | None = None      # originating signal
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Fill:
    """A single (possibly partial) fill event."""
    order_id: str
    instrument: str
    side: OrderSide
    quantity: int
    price: float
    commission: float = 0.0
    slippage: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class OrderState:
    """Mutable state tracking for a live order."""
    request: OrderRequest
    status: OrderStatus = OrderStatus.PENDING
    filled_qty: int = 0
    avg_fill_price: float = 0.0
    fills: list[Fill] = field(default_factory=list)
    reject_reason: str = ""
    broker_order_id: str = ""
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def apply_fill(self, fill: Fill) -> None:
        total_value = self.avg_fill_price * self.filled_qty + fill.price * fill.quantity
        self.filled_qty += fill.quantity
        self.avg_fill_price = total_value / self.filled_qty if self.filled_qty else 0.0
        self.fills.append(fill)
        self.updated_at = fill.timestamp
        if self.filled_qty >= self.request.quantity:
            self.status = OrderStatus.FILLED
        elif self.filled_qty > 0:
            self.status = OrderStatus.PARTIAL


# =====================================================================
#  Position tracking
# =====================================================================

@dataclass
class Position:
    """An open position in any execution mode."""
    instrument: str
    quantity: int = 0                   # positive = long, negative = short
    avg_entry_price: float = 0.0
    unrealised_pnl: float = 0.0
    realised_pnl: float = 0.0
    stop_loss: float | None = None
    take_profit: float | None = None
    trailing_stop_pct: float | None = None
    trailing_high: float = 0.0          # highest price since entry (for trailing)
    entry_time: datetime | None = None
    entry_bar_index: int = 0            # for max-holding-period exits
    total_charges: float = 0.0
    original_quantity: int = 0          # qty at entry (before partial TP)
    partial_tp_done: bool = False       # True after first scale-out
    atr_at_entry: float = 0.0           # ATR when position was opened

    @property
    def is_open(self) -> bool:
        return self.quantity != 0

    @property
    def side(self) -> str:
        if self.quantity > 0:
            return "long"
        if self.quantity < 0:
            return "short"
        return "flat"

    def mark_to_market(self, current_price: float) -> None:
        if self.quantity > 0:
            self.unrealised_pnl = (current_price - self.avg_entry_price) * self.quantity
            self.trailing_high = max(self.trailing_high, current_price)
        elif self.quantity < 0:
            self.unrealised_pnl = (self.avg_entry_price - current_price) * abs(self.quantity)


# =====================================================================
#  Portfolio state (shared across all modes)
# =====================================================================

@dataclass
class PortfolioState:
    """Snapshot of the portfolio passed to the strategy engine."""
    cash: float = 100_000.0
    positions: dict[str, Position] = field(default_factory=dict)
    daily_pnl: float = 0.0
    daily_trades: int = 0
    daily_losses: int = 0
    consecutive_losses: int = 0             # running count of consecutive losses
    total_commission: float = 0.0
    execution_mode: ExecutionMode = ExecutionMode.PAPER

    @property
    def equity(self) -> float:
        return self.cash + sum(
            p.unrealised_pnl + p.avg_entry_price * p.quantity
            for p in self.positions.values()
            if p.is_open
        )

    @property
    def open_position_count(self) -> int:
        return sum(1 for p in self.positions.values() if p.is_open)

    @property
    def gross_exposure(self) -> float:
        return sum(
            abs(p.quantity) * p.avg_entry_price
            for p in self.positions.values()
            if p.is_open
        )


# =====================================================================
#  Risk rules (shared across all execution modes)
# =====================================================================

@dataclass
class RiskLimits:
    """Risk constraints enforced identically in live, paper, and backtest."""
    max_position_pct: float = 0.20           # max 20% of equity per position
    max_gross_exposure_pct: float = 0.80     # max 80% gross
    max_positions: int = 8
    max_daily_loss_pct: float = 0.05         # 5% of equity
    max_loss_streak_trades: int = 5          # cooldown after 5 consecutive losses
    cooldown_bars: int = 3                   # bars to wait after loss streak
    min_signal_confidence: float = 0.53
    max_event_risk: float = 0.8              # skip if event_risk_score > 0.8
    stop_loss_pct: float = 0.05              # base stop-loss (overridden by ATR)
    take_profit_pct: float = 0.10            # base take-profit (overridden by ATR)
    trailing_stop_pct: float = 0.03          # 3% trailing stop
    max_holding_bars: int = 30               # force-close after N bars
    max_sector_exposure_pct: float = 0.40
    volatility_circuit_breaker: float = 0.50 # pause if annualised vol > 50%

    # --- Adaptive / ATR-based stops ---
    atr_stop_multiplier: float = 1.5         # SL = entry - ATR × 1.5
    atr_profit_multiplier: float = 4.0       # TP = entry + ATR × 4.0
    use_atr_stops: bool = True               # prefer ATR over fixed %

    # --- Regime scaling factors ---
    regime_scale_trending: float = 1.2       # upsize in trending markets
    regime_scale_range: float = 0.8          # slightly reduce in range-bound
    regime_scale_high_vol: float = 0.5       # cut size in high vol
    regime_scale_crash: float = 0.25         # minimal exposure in crashes

    # --- Partial profit booking ---
    partial_tp_enabled: bool = True
    partial_tp_fraction: float = 0.33        # close 33% of position
    partial_tp_trigger_pct: float = 0.5      # at 50% of TP target

    # --- Momentum confirmation ---
    require_momentum_confirm: bool = True    # skip if momentum opposes signal

    # --- Graduated loss response ---
    loss_streak_half_size: int = 3           # half size after 3 consecutive losses


# =====================================================================
#  Trade result (for logging / metrics)
# =====================================================================

@dataclass
class TradeResult:
    """Completed round-trip trade record."""
    trade_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    instrument: str = ""
    side: str = ""
    entry_price: float = 0.0
    exit_price: float = 0.0
    quantity: int = 0
    pnl: float = 0.0
    charges: float = 0.0
    slippage: float = 0.0
    holding_bars: int = 0
    entry_time: datetime | None = None
    exit_time: datetime | None = None
    exit_reason: str = ""       # "signal", "stop_loss", "take_profit", "trailing", "max_hold", "kill_switch"
    signal_confidence: float = 0.0
    regime_at_entry: str = ""
    execution_mode: str = ""
