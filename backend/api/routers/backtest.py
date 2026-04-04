# Backtesting endpoint
"""Backtest API endpoints."""

from __future__ import annotations

import logging
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
import threading

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from backend.api.schemas import (
    BacktestRunRequest,
    BacktestRunResponse,
    BacktestResultsResponse,
    BacktestTrade,
    JobStatus,
)
from backend.prediction_engine.backtest.backtester import Backtester, ExecutionConfig
from backend.prediction_engine.feature_store.feature_store import (
    build_features,
    _load_ticker_csv,
)
from backend.prediction_engine.training.trainer import NUMERIC_FEATURES
from backend.services.model_manager import ModelManager
from backend.services.data_downloader import download_symbol, _yf_ticker

import yfinance as yf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtest", tags=["backtest"])

STORAGE_RAW = Path(__file__).resolve().parents[3] / "storage" / "raw"

# In-memory job store (thread-safe; use Celery + DB in production)
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _ensure_backtest_data(
    tickers: list[str],
    start_date: str,
    end_date: str,
    work_dir: Path,
) -> list[Path]:
    """Copy existing CSVs to work_dir; download missing/insufficient data.

    Returns a list of temp CSV paths that were freshly downloaded (for cleanup).
    Feature computation needs ~200 rows before ``start_date`` for SMA-200 etc.,
    so we download with a generous look-back.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []

    lookback_start = (
        pd.Timestamp(start_date) - pd.DateOffset(days=400)
    ).strftime("%Y-%m-%d")

    for ticker in tickers:
        src = STORAGE_RAW / f"{ticker}.csv"
        dst = work_dir / f"{ticker}.csv"

        # Check if existing CSV covers the requested range
        if src.exists():
            try:
                df = pd.read_csv(src, parse_dates=["Date"])
                date_min, date_max = df["Date"].min(), df["Date"].max()
                if date_min <= pd.Timestamp(lookback_start) and date_max >= pd.Timestamp(end_date):
                    # Existing data fully covers needed range — just copy
                    shutil.copy2(src, dst)
                    logger.info("Backtest: reused existing CSV for %s", ticker)
                    continue
            except Exception:
                pass  # fall through to download

        # Download fresh data covering the full range
        logger.info("Backtest: downloading %s for %s → %s", ticker, lookback_start, end_date)
        ticker_str = _yf_ticker(ticker)
        try:
            t = yf.Ticker(ticker_str)
            raw = t.history(start=lookback_start, end=end_date)
            if raw is None or raw.empty:
                logger.warning("Backtest: no data returned for %s", ticker)
                continue
            raw = raw.reset_index()
            if "Datetime" in raw.columns:
                raw = raw.rename(columns={"Datetime": "Date"})
            if "Date" not in raw.columns:
                raw = raw.rename(columns={raw.columns[0]: "Date"})
            raw["Date"] = pd.to_datetime(raw["Date"]).dt.tz_localize(None)
            keep = [c for c in ["Date", "Open", "High", "Low", "Close", "Volume"] if c in raw.columns]
            raw = raw[keep].dropna(subset=["Close"])
            if raw.empty:
                continue
            raw.to_csv(dst, index=False)
            downloaded.append(dst)
            logger.info("Backtest: downloaded %d rows for %s", len(raw), ticker)
        except Exception as exc:
            logger.error("Backtest: failed to download %s: %s", ticker, exc)

    return downloaded


def _run_backtest_job(job_id: str, req_data: dict) -> None:
    """Execute the backtest in a background thread."""
    work_dir = STORAGE_RAW.parent / "backtests_tmp" / job_id
    try:
        with _jobs_lock:
            _jobs[job_id]["status"] = JobStatus.RUNNING

        tickers = req_data["tickers"]
        start_date = req_data["start_date"]
        end_date = req_data["end_date"]
        initial_capital = req_data.get("initial_capital", 100_000.0)

        # 1. Ensure data is available — download if needed
        _ensure_backtest_data(tickers, start_date, end_date, work_dir)

        # 2. Build feature matrix from the work directory
        features_df = build_features(tickers, start=start_date, end=end_date, data_dir=str(work_dir))

        # 3. Generate predictions using the loaded model
        mgr = ModelManager()
        if mgr.model is None:
            mgr.load_latest()
        model = mgr.model
        if model is None:
            raise RuntimeError("No prediction model available")

        numeric_cols = [c for c in NUMERIC_FEATURES if c in features_df.columns]
        X = features_df[numeric_cols]

        if X.empty:
            raise RuntimeError(
                f"No data available for {tickers} between {start_date} and {end_date}. "
                "The date range may be too old for available market data."
            )

        preds_raw = model.predict_with_expected_return(X)

        predictions_df = pd.DataFrame({
            "date": features_df["date"].values,
            "ticker": features_df["ticker"].values,
            "action": [p["action"] for p in preds_raw],
            "confidence": [p["confidence"] for p in preds_raw],
        })

        # Pass through feature columns needed by the strategy engine
        for col in ("atr_14", "volatility_20", "momentum_10", "ema_crossover",
                     "adx_14", "rsi_14", "distance_sma50"):
            if col in features_df.columns:
                predictions_df[col] = features_df[col].values

        # 4. Build price DataFrame from work directory CSVs
        price_frames = []
        for ticker in tickers:
            try:
                raw = _load_ticker_csv(ticker, work_dir)
                raw = raw[["Date", "Close"]].copy()
                raw["ticker"] = ticker
                raw = raw[(raw["Date"] >= pd.Timestamp(start_date)) & (raw["Date"] <= pd.Timestamp(end_date))]
                price_frames.append(raw)
            except FileNotFoundError:
                logger.warning("No price data for %s, skipping", ticker)
        if not price_frames:
            raise RuntimeError("No price data available for any requested ticker")

        price_df = pd.concat(price_frames, ignore_index=True)

        # 5. Run the backtester
        bt = Backtester(ExecutionConfig())
        bt.run(predictions_df, price_df, initial_capital=initial_capital, job_id=job_id)

        with _jobs_lock:
            _jobs[job_id]["status"] = JobStatus.COMPLETED

        logger.info("Backtest %s completed", job_id)

    except Exception as exc:
        logger.exception("Backtest %s failed", job_id)
        with _jobs_lock:
            _jobs[job_id]["status"] = JobStatus.FAILED
            _jobs[job_id]["error"] = str(exc)
    finally:
        # Clean up temporary data
        if work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)
            logger.info("Backtest %s: cleaned up temp data %s", job_id, work_dir)


@router.post("/run", response_model=BacktestRunResponse)
async def backtest_run(req: BacktestRunRequest):
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    job = {
        "request": req.model_dump(),
        "status": JobStatus.PENDING,
        "submitted_at": now,
    }

    with _jobs_lock:
        _jobs[job_id] = job

    # Run in a background thread so the endpoint returns immediately
    thread = threading.Thread(
        target=_run_backtest_job,
        args=(job_id, req.model_dump()),
        daemon=True,
    )
    thread.start()

    return BacktestRunResponse(
        job_id=uuid.UUID(job_id),
        status=JobStatus.PENDING,
        submitted_at=now,
    )


@router.get("/{job_id}/results", response_model=BacktestResultsResponse)
async def backtest_results(job_id: str):
    # Try loading from disk first (completed jobs persist to JSON)
    result = Backtester.load_result(job_id)
    if result:
        trades = [
            BacktestTrade(**t) for t in result.get("trades", [])
        ]
        return BacktestResultsResponse(
            job_id=uuid.UUID(result["job_id"]),
            status=JobStatus.COMPLETED,
            tickers=result["tickers"],
            start_date=result["start_date"],
            end_date=result["end_date"],
            initial_capital=result["initial_capital"],
            final_value=result["final_value"],
            total_return_pct=result["total_return_pct"],
            sharpe_ratio=result.get("sharpe_ratio"),
            sortino_ratio=result.get("sortino_ratio"),
            max_drawdown_pct=result.get("max_drawdown_pct"),
            cagr_pct=result.get("cagr_pct"),
            total_charges=result.get("total_charges", 0),
            win_rate=result.get("win_rate"),
            avg_win=result.get("avg_win"),
            avg_loss=result.get("avg_loss"),
            expectancy=result.get("expectancy"),
            total_trades=result.get("total_trades", 0),
            no_trade_count=result.get("no_trade_count", 0),
            rejection_count=result.get("rejection_count", 0),
            trades=trades,
            completed_at=result.get("completed_at"),
        )

    # Check in-memory jobs for pending/running/failed status
    with _jobs_lock:
        if job_id in _jobs:
            job = _jobs[job_id]
            status = job["status"]
            # Return status as 200 JSON so the frontend polling can read it
            return JSONResponse(
                status_code=200,
                content={
                    "job_id": job_id,
                    "status": status.value,
                    "tickers": job["request"]["tickers"],
                    "start_date": job["request"]["start_date"],
                    "end_date": job["request"]["end_date"],
                    "initial_capital": job["request"].get("initial_capital", 100000),
                    "final_value": 0,
                    "total_return_pct": 0,
                    "trades": [],
                    "completed_at": None,
                    "error": job.get("error"),
                },
            )

    raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
