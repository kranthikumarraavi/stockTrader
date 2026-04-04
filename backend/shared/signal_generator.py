"""Enhanced signal generator.

Wraps the existing prediction engine (LightGBM / ensemble) and
produces ``TradingSignal`` objects conforming to the shared schema.
Enriches raw model outputs with regime, volatility, event risk, and
confidence calibration so downstream consumers (strategy engine,
backtest, paper) receive actionable, risk-aware signals.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from backend.shared.schemas import (
    RegimeLabel,
    SignalDirection,
    TradingSignal,
)

logger = logging.getLogger(__name__)


# =====================================================================
#  Regime mapping (from existing regime_detector output)
# =====================================================================

_REGIME_MAP: dict[str, RegimeLabel] = {
    "trending_up": RegimeLabel.TRENDING_UP,
    "trending_down": RegimeLabel.TRENDING_DOWN,
    "range_bound": RegimeLabel.RANGE_BOUND,
    "high_volatility": RegimeLabel.HIGH_VOLATILITY,
    "low_volatility": RegimeLabel.LOW_VOLATILITY,
    "gap_up": RegimeLabel.BREAKOUT,
    "gap_down": RegimeLabel.BREAKOUT,
    "crash": RegimeLabel.CRASH,
}


def _map_regime(regime_str: str) -> RegimeLabel:
    return _REGIME_MAP.get(regime_str.lower(), RegimeLabel.UNKNOWN)


# =====================================================================
#  Signal generator
# =====================================================================

class SignalGenerator:
    """Produces ``TradingSignal`` from the existing prediction pipeline.

    Usage
    -----
    >>> gen = SignalGenerator(model, regime_detector)
    >>> signals = gen.generate(features_dict_list, prices_dict, timestamp)
    """

    def __init__(
        self,
        model: Any = None,              # backend.prediction_engine.models.base_model.BaseModel
        regime_detector: Any = None,     # backend.services.regime_detector.RegimeDetector
        model_version: str = "",
        confidence_threshold: float = 0.55,
        no_trade_band: float = 0.05,     # abstain if P(up) ∈ [0.5 - band, 0.5 + band]
    ) -> None:
        self._model = model
        self._regime = regime_detector
        self._model_version = model_version
        self._confidence_threshold = confidence_threshold
        self._no_trade_band = no_trade_band

    # ------------------------------------------------------------------
    #  Core generation
    # ------------------------------------------------------------------

    def generate_signals(
        self,
        feature_rows: list[dict[str, Any]],
        prices: dict[str, float],
        timestamp: datetime | None = None,
        regime_overrides: dict[str, str] | None = None,
    ) -> list[TradingSignal]:
        """Generate signals for one or more instruments at a single point in time.

        Parameters
        ----------
        feature_rows
            List of feature dicts, each must have ``ticker`` key.
        prices
            Current market prices keyed by ticker.
        timestamp
            Decision timestamp.  Must NOT be in the future.
        regime_overrides
            Optional per-ticker regime string (e.g., from a pre-computed cache).
        """
        ts = timestamp or datetime.now(timezone.utc)
        if not feature_rows:
            return []

        df = pd.DataFrame(feature_rows)
        tickers = df["ticker"].tolist()

        # Get model predictions
        from backend.prediction_engine.training.trainer import NUMERIC_FEATURES
        available_features = [c for c in NUMERIC_FEATURES if c in df.columns]
        if not available_features:
            logger.warning("No numeric features available for prediction.")
            return []

        X = df[available_features].fillna(0)

        # Predict probabilities
        if self._model is None:
            logger.warning("No model loaded — returning empty signals.")
            return []

        proba = self._model.predict_proba(X)
        if proba.ndim == 2 and proba.shape[1] >= 2:
            p_up = proba[:, 1] if proba.shape[1] == 2 else proba[:, 2]
        else:
            p_up = proba

        signals: list[TradingSignal] = []

        for i, ticker in enumerate(tickers):
            prob_up = float(p_up[i])
            prob_down = 1.0 - prob_up

            # Regime
            regime_str = ""
            if regime_overrides and ticker in regime_overrides:
                regime_str = regime_overrides[ticker]
            elif self._regime:
                try:
                    result = self._regime.detect(ticker)
                    regime_str = result.regime.value if hasattr(result, "regime") else str(result.get("regime", ""))
                except Exception:
                    regime_str = "unknown"
            regime = _map_regime(regime_str) if regime_str else RegimeLabel.UNKNOWN

            # Volatility estimate from features
            vol = float(df.iloc[i].get("volatility_20", 0.20))

            # Expected move — direction_probability * vol (rough estimate)
            expected_move = (prob_up - 0.5) * vol * 2  # centered around 0

            # Confidence = distance from 0.5
            raw_confidence = abs(prob_up - 0.5) * 2  # 0 to 1

            # Direction
            no_trade_lo = 0.5 - self._no_trade_band
            no_trade_hi = 0.5 + self._no_trade_band
            no_trade = no_trade_lo <= prob_up <= no_trade_hi

            if prob_up > 0.5:
                direction = SignalDirection.LONG
            elif prob_up < 0.5:
                direction = SignalDirection.SHORT
            else:
                direction = SignalDirection.FLAT

            if no_trade or raw_confidence < self._confidence_threshold:
                direction = SignalDirection.FLAT
                no_trade = True

            # Top features from model (SHAP or built-in importance)
            top_feats: list[tuple[str, float]] = []
            try:
                if hasattr(self._model, "model") and hasattr(self._model.model, "feature_importance"):
                    importances = self._model.model.feature_importance(importance_type="gain")
                    feat_names = available_features
                    if len(importances) == len(feat_names):
                        pairs = sorted(zip(feat_names, importances), key=lambda x: -x[1])
                        top_feats = [(n, round(float(v), 4)) for n, v in pairs[:5]]
            except Exception:
                pass

            # Holding horizon heuristic
            if regime in (RegimeLabel.HIGH_VOLATILITY, RegimeLabel.CRASH):
                horizon = 1
            elif regime in (RegimeLabel.TRENDING_UP, RegimeLabel.TRENDING_DOWN):
                horizon = 5
            else:
                horizon = 3

            price = prices.get(ticker, 0.0)

            # Extract feature metadata for strategy engine
            row = df.iloc[i]
            atr = float(row.get("atr_14", 0.0)) if "atr_14" in df.columns else 0.0
            momentum = float(row.get("momentum_10", 0.0)) if "momentum_10" in df.columns else 0.0
            ema_cross = float(row.get("ema_crossover", 0.0)) if "ema_crossover" in df.columns else 0.0
            adx = float(row.get("adx_14", 0.0)) if "adx_14" in df.columns else 0.0
            rsi = float(row.get("rsi_14", 50.0)) if "rsi_14" in df.columns else 50.0

            signals.append(TradingSignal(
                instrument=ticker,
                timestamp=ts,
                timeframe="1d",
                signal_direction=direction,
                direction_probability=round(prob_up, 4),
                expected_move=round(expected_move, 6),
                expected_volatility=round(vol, 4),
                confidence_score=round(raw_confidence, 4),
                regime_label=regime,
                event_risk_score=0.0,     # placeholder — enriched later
                sentiment_score=0.0,      # placeholder — enriched later
                no_trade_flag=no_trade,
                model_version=self._model_version,
                top_features=top_feats,
                recommended_holding_horizon=horizon,
                metadata={
                    "price": price,
                    "atr_14": atr,
                    "momentum_10": momentum,
                    "ema_crossover": ema_cross,
                    "adx_14": adx,
                    "rsi_14": rsi,
                },
            ))

        return signals

    # ------------------------------------------------------------------
    #  Single-ticker convenience
    # ------------------------------------------------------------------

    def generate_single(
        self,
        features: dict[str, Any],
        price: float,
        timestamp: datetime | None = None,
        regime_override: str | None = None,
    ) -> TradingSignal | None:
        ticker = features.get("ticker", "UNKNOWN")
        overrides = {ticker: regime_override} if regime_override else None
        results = self.generate_signals([features], {ticker: price}, timestamp, overrides)
        return results[0] if results else None
