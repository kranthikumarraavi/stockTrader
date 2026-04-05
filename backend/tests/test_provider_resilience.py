# Market data provider resilience tests
"""Tests for provider retry/caching/fallback behavior."""

from __future__ import annotations

import pandas as pd

from backend.prediction_engine.data_pipeline.providers import (
    MarketDataProvider,
    ProviderChain,
    ProviderConfig,
    ProviderError,
    SymbolMapper,
    YahooMarketDataProvider,
)


class _FlakyYahoo:
    def __init__(self) -> None:
        self.calls = 0

    def download(self, *args, **kwargs):  # pragma: no cover - called by provider
        self.calls += 1
        if self.calls == 1:
            raise Exception("Too Many Requests. Rate limited. Try after a while.")
        return pd.DataFrame(
            {
                "Date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
                "Open": [100.0, 101.0, 102.0],
                "High": [101.0, 102.0, 103.0],
                "Low": [99.0, 100.0, 101.0],
                "Close": [100.5, 101.5, 102.5],
                "Volume": [10_000, 11_000, 12_000],
            }
        )


class _FailingProvider(MarketDataProvider):
    def get_historical_bars(self, symbol, start, end, interval="1d"):
        raise ProviderError("Primary failed", reason="rate_limited", details={"symbol": symbol})

    def get_latest_quote(self, symbol):
        raise ProviderError("Primary failed", reason="rate_limited", details={"symbol": symbol})

    def get_market_status(self, exchange):
        raise ProviderError("Primary failed", reason="rate_limited", details={"exchange": exchange})


class _FallbackProvider(MarketDataProvider):
    def get_historical_bars(self, symbol, start, end, interval="1d"):
        return pd.DataFrame(
            {
                "Date": pd.to_datetime(["2026-02-01"]),
                "Open": [10.0],
                "High": [10.5],
                "Low": [9.5],
                "Close": [10.2],
                "Volume": [1_000],
            }
        )

    def get_latest_quote(self, symbol):
        return {"symbol": symbol, "price": 10.2}

    def get_market_status(self, exchange):
        return {"exchange": exchange, "status": "open"}


def test_symbol_mapper_normalizes_india_tickers():
    mapper = SymbolMapper()
    assert mapper.to_yahoo("RELIANCE") == "RELIANCE.NS"
    assert mapper.to_yahoo("BAJAJ_AUTO") == "BAJAJ-AUTO.NS"
    assert mapper.to_yahoo("M_M") == "M&M.NS"
    assert mapper.to_yahoo("BANKNIFTY") == "^NSEBANK"


def test_yahoo_provider_retries_and_caches(monkeypatch, tmp_path):
    flaky = _FlakyYahoo()
    monkeypatch.setattr("backend.prediction_engine.data_pipeline.providers.yf", flaky)

    provider = YahooMarketDataProvider(
        config=ProviderConfig(
            requests_per_second=1000.0,
            max_retries=3,
            backoff_base_s=0.0,
            backoff_jitter_s=0.0,
            historical_cache_ttl_s=3600,
            symbol_cooldown_s=1,
            circuit_failure_threshold=10,
            circuit_cooldown_s=1,
        ),
        cache_dir=tmp_path,
    )

    df_first = provider.get_historical_bars("RELIANCE", "2026-01-01", "2026-01-10")
    assert not df_first.empty
    assert flaky.calls == 2  # first call fails, second succeeds

    # Second call should hit cache and avoid another provider call.
    df_second = provider.get_historical_bars("RELIANCE", "2026-01-01", "2026-01-10")
    assert flaky.calls == 2
    pd.testing.assert_frame_equal(df_first, df_second)


def test_provider_chain_uses_fallback():
    chain = ProviderChain([_FailingProvider(), _FallbackProvider()])
    df = chain.get_historical_bars("RELIANCE", "2026-02-01", "2026-02-02")
    assert len(df) == 1
    assert float(df.iloc[0]["Close"]) == 10.2
