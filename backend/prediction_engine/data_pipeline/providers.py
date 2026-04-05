"""Market data provider abstraction with retries, cache, and cooldowns.

This module centralizes market-data ingestion resilience so training,
backtesting, and runtime refresh all use consistent behavior.
"""

from __future__ import annotations

import abc
import hashlib
import json
import logging
import os
import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
except ImportError:  # pragma: no cover - environment dependent
    yf = None


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CACHE_DIR = REPO_ROOT / "storage" / "cache" / "market_data"


class ProviderError(RuntimeError):
    """Raised when provider fetch fails after retries."""

    def __init__(
        self,
        message: str,
        *,
        reason: str = "provider_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.details = details or {}


class CircuitOpenError(ProviderError):
    """Raised when provider circuit breaker is open."""


@dataclass(frozen=True)
class ProviderConfig:
    """Resilience controls for market-data providers."""

    requests_per_second: float = 0.6
    max_retries: int = 4
    backoff_base_s: float = 1.5
    backoff_jitter_s: float = 0.75
    historical_cache_ttl_s: int = 60 * 60
    quote_cache_ttl_s: int = 20
    symbol_cooldown_s: int = 120
    circuit_failure_threshold: int = 8
    circuit_cooldown_s: int = 90


class MarketDataProvider(abc.ABC):
    """Provider contract used by market-data ingestion paths."""

    @abc.abstractmethod
    def get_historical_bars(
        self,
        symbol: str,
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        raise NotImplementedError

    @abc.abstractmethod
    def get_latest_quote(self, symbol: str) -> dict[str, Any]:
        raise NotImplementedError

    @abc.abstractmethod
    def get_market_status(self, exchange: str) -> dict[str, Any]:
        raise NotImplementedError


class SymbolMapper:
    """Canonical symbol mapping for provider-specific tickers."""

    INDEX_MAP: dict[str, str] = {
        "NIFTY50": "^NSEI",
        "BANKNIFTY": "^NSEBANK",
        "SENSEX": "^BSESN",
    }
    SYMBOL_OVERRIDES: dict[str, str] = {
        "BAJAJ_AUTO": "BAJAJ-AUTO",
        "M_M": "M&M",
    }

    def __init__(self, nse_suffix: str = ".NS") -> None:
        self._nse_suffix = nse_suffix

    def normalize_symbol(self, symbol: str) -> str:
        if not symbol:
            return symbol
        base = symbol.strip().upper()
        if base.endswith(".NS"):
            return base[:-3]
        if base.endswith(".BO"):
            return base[:-3]
        return base

    def to_yahoo(self, symbol: str) -> str:
        base = self.normalize_symbol(symbol)
        if base in self.INDEX_MAP:
            return self.INDEX_MAP[base]

        mapped = self.SYMBOL_OVERRIDES.get(base, base)
        if "_" in mapped:
            parts = [p for p in mapped.split("_") if p]
            if all(len(p) == 1 for p in parts):
                mapped = "&".join(parts)
            else:
                mapped = "-".join(parts)
        return f"{mapped}{self._nse_suffix}"


class RequestRateLimiter:
    """Simple thread-safe rate limiter (minimum spacing between requests)."""

    def __init__(self, requests_per_second: float) -> None:
        self._min_interval = 1.0 / max(requests_per_second, 1e-6)
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait_for = self._next_allowed - now
            if wait_for > 0:
                time.sleep(wait_for)
            now2 = time.monotonic()
            self._next_allowed = now2 + self._min_interval


class CircuitBreaker:
    """Failure-based circuit breaker with cool-down recovery."""

    def __init__(self, failure_threshold: int, cooldown_s: int) -> None:
        self._failure_threshold = max(1, int(failure_threshold))
        self._cooldown_s = max(1, int(cooldown_s))
        self._failures = 0
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    def check_open(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return False
            if time.monotonic() - self._opened_at >= self._cooldown_s:
                self._opened_at = None
                self._failures = 0
                return False
            return True

    def on_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def on_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self._failure_threshold:
                self._opened_at = time.monotonic()


class FileTTLCache:
    """CSV-backed TTL cache for provider responses."""

    def __init__(self, cache_dir: Path) -> None:
        self._dir = Path(cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _paths(self, key: str) -> tuple[Path, Path]:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        csv_path = self._dir / f"{digest}.csv"
        meta_path = self._dir / f"{digest}.meta.json"
        return csv_path, meta_path

    def get(self, key: str, ttl_s: int) -> pd.DataFrame | None:
        csv_path, meta_path = self._paths(key)
        if not csv_path.exists() or not meta_path.exists():
            return None
        try:
            metadata = json.loads(meta_path.read_text())
            created_at = float(metadata.get("created_at_epoch", 0))
            age_s = time.time() - created_at
            if age_s > max(0, ttl_s):
                return None
            df = pd.read_csv(csv_path, parse_dates=["Date"])
            return df
        except Exception:
            return None

    def set(self, key: str, df: pd.DataFrame, metadata: dict[str, Any] | None = None) -> None:
        csv_path, meta_path = self._paths(key)
        payload = {
            "created_at_epoch": time.time(),
            **(metadata or {}),
        }
        with self._lock:
            df.to_csv(csv_path, index=False)
            meta_path.write_text(json.dumps(payload))


class YahooMarketDataProvider(MarketDataProvider):
    """Yahoo implementation with retry, cache, throttling, and cooldown."""

    REQUIRED_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume"]

    def __init__(
        self,
        *,
        config: ProviderConfig | None = None,
        cache_dir: Path | None = None,
        mapper: SymbolMapper | None = None,
    ) -> None:
        self._config = config or ProviderConfig()
        self._cache = FileTTLCache(cache_dir or DEFAULT_CACHE_DIR)
        self._mapper = mapper or SymbolMapper()
        self._rate_limiter = RequestRateLimiter(self._config.requests_per_second)
        self._circuit = CircuitBreaker(
            failure_threshold=self._config.circuit_failure_threshold,
            cooldown_s=self._config.circuit_cooldown_s,
        )
        self._symbol_cooldown_until: dict[str, float] = {}
        self._cooldown_lock = threading.Lock()

    @staticmethod
    def _as_date_str(v: str | datetime) -> str:
        if isinstance(v, datetime):
            return v.strftime("%Y-%m-%d")
        return str(v)[:10]

    @staticmethod
    def _is_rate_limited(exc: Exception) -> bool:
        msg = str(exc).lower()
        return "rate limit" in msg or "too many requests" in msg

    def _cache_key(self, symbol: str, start: str, end: str, interval: str) -> str:
        return f"yahoo:{symbol}:{start}:{end}:{interval}"

    def _check_symbol_cooldown(self, symbol: str) -> None:
        with self._cooldown_lock:
            until = self._symbol_cooldown_until.get(symbol, 0.0)
        now = time.monotonic()
        if until > now:
            raise ProviderError(
                f"Symbol {symbol} is in cooldown for {until - now:.1f}s",
                reason="symbol_cooldown",
                details={"symbol": symbol, "cooldown_remaining_s": round(until - now, 3)},
            )

    def _apply_symbol_cooldown(self, symbol: str, attempt: int) -> None:
        cool_s = self._config.symbol_cooldown_s * max(1, attempt)
        with self._cooldown_lock:
            self._symbol_cooldown_until[symbol] = time.monotonic() + cool_s

    def _normalize_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if "Date" not in df.columns:
            df = df.reset_index()
        if "Date" not in df.columns and len(df.columns) > 0:
            df = df.rename(columns={df.columns[0]: "Date"})

        missing = [c for c in self.REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ProviderError(
                "Provider response missing required columns",
                reason="invalid_response",
                details={"missing_columns": missing},
            )
        out = df[self.REQUIRED_COLUMNS].copy()
        out["Date"] = pd.to_datetime(out["Date"]).dt.tz_localize(None)
        out = out.dropna(subset=["Close"]).sort_values("Date").reset_index(drop=True)
        return out

    def get_historical_bars(
        self,
        symbol: str,
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        if yf is None:
            raise ProviderError("yfinance is not installed", reason="dependency_missing")

        canonical = self._mapper.normalize_symbol(symbol)
        start_str = self._as_date_str(start)
        end_str = self._as_date_str(end)
        key = self._cache_key(canonical, start_str, end_str, interval)

        cached = self._cache.get(key, self._config.historical_cache_ttl_s)
        if cached is not None and not cached.empty:
            return cached

        if self._circuit.check_open():
            raise CircuitOpenError(
                "Yahoo provider circuit is open",
                reason="provider_circuit_open",
                details={"provider": "yahoo"},
            )

        self._check_symbol_cooldown(canonical)
        yahoo_symbol = self._mapper.to_yahoo(canonical)

        last_exc: Exception | None = None
        for attempt in range(1, self._config.max_retries + 1):
            self._rate_limiter.wait()
            try:
                raw = yf.download(
                    yahoo_symbol,
                    start=start_str,
                    end=end_str,
                    interval=interval,
                    auto_adjust=False,
                    progress=False,
                    threads=False,
                )
                if raw is None or raw.empty:
                    raise ProviderError(
                        f"No data returned for {canonical}",
                        reason="empty_response",
                        details={"symbol": canonical, "provider_symbol": yahoo_symbol},
                    )
                frame = self._normalize_frame(raw)
                if frame.empty:
                    raise ProviderError(
                        f"No usable rows returned for {canonical}",
                        reason="empty_rows",
                        details={"symbol": canonical},
                    )
                self._cache.set(
                    key,
                    frame,
                    metadata={
                        "symbol": canonical,
                        "provider_symbol": yahoo_symbol,
                        "provider": "yahoo",
                        "interval": interval,
                    },
                )
                self._circuit.on_success()
                return frame
            except Exception as exc:  # pragma: no cover - depends on provider behavior
                last_exc = exc
                self._circuit.on_failure()
                rate_limited = self._is_rate_limited(exc)
                if rate_limited:
                    self._apply_symbol_cooldown(canonical, attempt)

                if attempt >= self._config.max_retries:
                    break
                backoff = self._config.backoff_base_s * (2 ** (attempt - 1))
                backoff += random.uniform(0.0, self._config.backoff_jitter_s)
                logger.warning(
                    "Yahoo fetch failed (%s, attempt %d/%d): %s; retrying in %.2fs",
                    canonical,
                    attempt,
                    self._config.max_retries,
                    exc,
                    backoff,
                )
                time.sleep(backoff)

        reason = "rate_limited" if (last_exc and self._is_rate_limited(last_exc)) else "provider_error"
        raise ProviderError(
            f"Yahoo fetch failed for {canonical}",
            reason=reason,
            details={
                "symbol": canonical,
                "provider_symbol": yahoo_symbol,
                "start": start_str,
                "end": end_str,
                "attempts": self._config.max_retries,
                "error": str(last_exc) if last_exc else "unknown",
            },
        ) from last_exc

    def get_latest_quote(self, symbol: str) -> dict[str, Any]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=7)
        df = self.get_historical_bars(symbol, start, end, interval="1d")
        if df.empty:
            raise ProviderError(
                f"No quote data for {symbol}",
                reason="empty_response",
                details={"symbol": symbol},
            )
        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else last
        price = float(last["Close"])
        prev_close = float(prev["Close"])
        change = price - prev_close
        change_pct = (change / prev_close * 100.0) if prev_close else 0.0
        return {
            "symbol": self._mapper.normalize_symbol(symbol),
            "price": round(price, 4),
            "prev_close": round(prev_close, 4),
            "change": round(change, 4),
            "change_pct": round(change_pct, 4),
            "timestamp": pd.to_datetime(last["Date"]).to_pydatetime().isoformat(),
            "provider": "yahoo",
        }

    def get_market_status(self, exchange: str) -> dict[str, Any]:
        return {
            "exchange": exchange,
            "status": "unknown",
            "provider": "yahoo",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class KiteProviderStub(MarketDataProvider):
    """Stub for Zerodha Kite integration (fallback-ready interface)."""

    def get_historical_bars(
        self,
        symbol: str,
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        raise NotImplementedError(
            "KiteProviderStub is not implemented yet. "
            "Set DATA_PROVIDER=yahoo until Zerodha integration is added."
        )

    def get_latest_quote(self, symbol: str) -> dict[str, Any]:
        raise NotImplementedError("KiteProviderStub.get_latest_quote is not implemented.")

    def get_market_status(self, exchange: str) -> dict[str, Any]:
        raise NotImplementedError("KiteProviderStub.get_market_status is not implemented.")


class ProviderChain(MarketDataProvider):
    """Try providers in order; fall back on provider errors."""

    def __init__(self, providers: list[MarketDataProvider]) -> None:
        if not providers:
            raise ValueError("ProviderChain requires at least one provider")
        self._providers = providers

    def _call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        errors: list[dict[str, Any]] = []
        for provider in self._providers:
            name = provider.__class__.__name__
            try:
                return getattr(provider, method)(*args, **kwargs)
            except NotImplementedError as exc:
                errors.append({"provider": name, "reason": "not_implemented", "error": str(exc)})
            except ProviderError as exc:
                errors.append({"provider": name, "reason": exc.reason, "error": str(exc), **exc.details})
            except Exception as exc:  # pragma: no cover - defensive
                errors.append({"provider": name, "reason": "unexpected_error", "error": str(exc)})
        raise ProviderError(
            f"All providers failed for method={method}",
            reason="all_providers_failed",
            details={"method": method, "errors": errors},
        )

    def get_historical_bars(
        self,
        symbol: str,
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        return self._call("get_historical_bars", symbol, start, end, interval=interval)

    def get_latest_quote(self, symbol: str) -> dict[str, Any]:
        return self._call("get_latest_quote", symbol)

    def get_market_status(self, exchange: str) -> dict[str, Any]:
        return self._call("get_market_status", exchange)


def create_default_provider_chain() -> ProviderChain:
    """Default provider chain: Yahoo primary, Kite stub fallback."""

    config = ProviderConfig(
        requests_per_second=float(os.getenv("YF_REQUESTS_PER_SECOND", "0.6")),
        max_retries=int(os.getenv("YF_MAX_RETRIES", "4")),
        backoff_base_s=float(os.getenv("YF_BACKOFF_BASE_S", "1.5")),
        backoff_jitter_s=float(os.getenv("YF_BACKOFF_JITTER_S", "0.75")),
        historical_cache_ttl_s=int(os.getenv("YF_CACHE_TTL_S", "3600")),
        quote_cache_ttl_s=int(os.getenv("YF_QUOTE_CACHE_TTL_S", "20")),
        symbol_cooldown_s=int(os.getenv("YF_SYMBOL_COOLDOWN_S", "120")),
        circuit_failure_threshold=int(os.getenv("YF_CIRCUIT_FAILURE_THRESHOLD", "8")),
        circuit_cooldown_s=int(os.getenv("YF_CIRCUIT_COOLDOWN_S", "90")),
    )
    cache_dir = Path(os.getenv("MARKET_DATA_CACHE_DIR", str(DEFAULT_CACHE_DIR)))
    return ProviderChain(
        [
            YahooMarketDataProvider(config=config, cache_dir=cache_dir),
            KiteProviderStub(),
        ]
    )

