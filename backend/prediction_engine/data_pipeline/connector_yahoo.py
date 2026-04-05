"""Yahoo connector facade backed by resilient provider chain."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from backend.prediction_engine.data_pipeline.providers import (
    ProviderChain,
    ProviderConfig,
    create_default_provider_chain,
)

logger = logging.getLogger(__name__)


class YahooConnector:
    """Backward-compatible connector API used across the codebase."""

    REQUIRED_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]

    def __init__(
        self,
        nse_suffix: str = ".NS",
        max_retries: int = 3,
        retry_delay_s: float = 1.0,
        provider_chain: ProviderChain | None = None,
    ) -> None:
        # Keep constructor args for compatibility with existing call-sites.
        if provider_chain is not None:
            self._providers = provider_chain
            return

        # Use defaults from env but allow caller overrides for retry/backoff.
        chain = create_default_provider_chain()
        if max_retries > 0 or retry_delay_s > 0:
            # Rebuild with explicit override so existing callers still influence behavior.
            from backend.prediction_engine.data_pipeline.providers import (
                YahooMarketDataProvider,
                KiteProviderStub,
                DEFAULT_CACHE_DIR,
            )
            cfg = ProviderConfig(
                max_retries=max(1, int(max_retries)),
                backoff_base_s=max(0.1, float(retry_delay_s)),
            )
            self._providers = ProviderChain(
                [YahooMarketDataProvider(config=cfg, cache_dir=DEFAULT_CACHE_DIR), KiteProviderStub()]
            )
        else:
            self._providers = chain

    def fetch(
        self,
        ticker: str,
        start: str | datetime,
        end: str | datetime,
    ) -> pd.DataFrame:
        """Download OHLCV data for a single ticker."""
        df = self._providers.get_historical_bars(ticker, start, end, interval="1d")
        if df is None or df.empty:
            logger.warning("No data returned for %s", ticker)
            return pd.DataFrame(columns=["Date"] + self.REQUIRED_COLUMNS)
        return df[["Date"] + self.REQUIRED_COLUMNS].copy()

    def fetch_to_csv(
        self,
        ticker: str,
        start: str | datetime,
        end: str | datetime,
        output_dir: str | Path,
    ) -> Path:
        """Fetch data and persist as CSV."""
        df = self.fetch(ticker, start, end)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{ticker}.csv"
        df.to_csv(path, index=False)
        logger.info("Saved %d rows -> %s", len(df), path)
        return path
