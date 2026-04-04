"""Portfolio intelligence API endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["portfolio-intelligence"])
logger = logging.getLogger(__name__)


def _pi():
    from backend.services.portfolio_intelligence import get_portfolio_intelligence
    return get_portfolio_intelligence()


def _ensure_dict(val) -> dict:
    """Convert list to empty dict if needed — positions must be dict[str, dict]."""
    if isinstance(val, dict):
        return val
    return {}


@router.post("/portfolio/metrics")
async def compute_metrics(payload: dict):
    """Compute comprehensive portfolio metrics."""
    try:
        metrics = _pi().compute_metrics(
            equity_curve=payload.get("equity_curve", []),
            trades=payload.get("trades", []),
            positions=_ensure_dict(payload.get("positions")),
            cash=float(payload.get("cash", 0)),
            initial_capital=float(payload.get("initial_capital", 100000)),
        )
        return metrics.to_dict()
    except Exception as exc:
        logger.exception("Portfolio endpoint error")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/portfolio/exposure")
async def exposure_heatmap(payload: dict):
    """Exposure heatmap by sector and instrument type."""
    try:
        return _pi().exposure_heatmap(_ensure_dict(payload.get("positions")))
    except Exception as exc:
        logger.exception("exposure_heatmap failed")
        return {}


@router.post("/portfolio/allocation")
async def capital_allocation(payload: dict):
    """Capital allocation recommendation based on regime."""
    try:
        return _pi().capital_allocation_recommendation(
            total_capital=float(payload.get("total_capital", 100000)),
            current_positions=_ensure_dict(payload.get("current_positions")),
            regime=payload.get("regime", "range_bound"),
        )
    except Exception as exc:
        logger.exception("Portfolio endpoint error")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/portfolio/daily-summary")
async def daily_summary(payload: dict):
    """End-of-day portfolio summary."""
    try:
        return _pi().daily_summary(
            equity_curve=payload.get("equity_curve", []),
            trades_today=payload.get("trades_today", []),
            positions=_ensure_dict(payload.get("positions")),
        )
    except Exception as exc:
        logger.exception("Portfolio endpoint error")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/portfolio/snapshot")
async def portfolio_snapshot():
    """Aggregate portfolio snapshot from paper trading accounts.

    Pulls positions, equity curves, and trade logs from all paper accounts
    and feeds them through portfolio intelligence analytics so the frontend
    doesn't need to pre-fetch and assemble data.
    """
    from backend.paper_trading.paper_account import PaperAccountManager

    mgr = PaperAccountManager()
    accounts = mgr.list_accounts()

    # Merge data from all paper accounts
    all_positions: dict[str, dict] = {}
    all_equity_curve: list[dict] = []
    all_trades: list[dict] = []
    total_cash = 0.0
    total_initial = 0.0

    for acct in accounts:
        total_cash += acct.cash
        total_initial += acct.initial_cash
        for ticker, pos in acct.positions.items():
            if pos.quantity != 0:
                all_positions[ticker] = {
                    "ticker": ticker,
                    "quantity": pos.quantity,
                    "avg_price": pos.avg_price,
                    "current_price": pos.current_price if hasattr(pos, "current_price") else pos.avg_price,
                }
        all_equity_curve.extend(acct.equity_curve)
        all_trades.extend(acct.trade_log)

    # If no accounts exist, return sensible defaults
    if not accounts:
        total_cash = 100_000.0
        total_initial = 100_000.0

    pi = _pi()

    try:
        metrics = pi.compute_metrics(
            equity_curve=all_equity_curve,
            trades=all_trades,
            positions=all_positions,
            cash=total_cash,
            initial_capital=total_initial,
        ).to_dict()
    except Exception as exc:
        logger.warning("snapshot metrics failed: %s", exc)
        metrics = {}

    try:
        exposure = pi.exposure_heatmap(all_positions)
    except Exception:
        exposure = {}

    try:
        allocation = pi.capital_allocation_recommendation(
            total_capital=total_cash + sum(
                p.get("quantity", 0) * p.get("current_price", p.get("avg_price", 0))
                for p in all_positions.values()
            ),
            current_positions=all_positions,
        )
    except Exception:
        allocation = {}

    # Build holdings list from positions
    holdings = [
        {
            "ticker": ticker,
            "quantity": p["quantity"],
            "avg_price": p["avg_price"],
            "current_price": p.get("current_price", p["avg_price"]),
            "pnl": (p.get("current_price", p["avg_price"]) - p["avg_price"]) * p["quantity"],
        }
        for ticker, p in all_positions.items()
    ]

    # Build equity curve points
    sorted_curve = sorted(all_equity_curve, key=lambda x: x.get("date", x.get("timestamp", "")))
    equity_points = [
        {"date": pt.get("date", pt.get("timestamp", "")), "equity": pt.get("equity", 0)}
        for pt in sorted_curve
    ]

    return {
        "metrics": metrics,
        "positions": list(all_positions.values()),
        "holdings": holdings,
        "equity_curve": equity_points,
        "exposure": exposure,
        "allocation": allocation,
        "accounts_count": len(accounts),
    }
