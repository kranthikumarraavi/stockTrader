# Gateway URL normalization tests
"""Regression tests for service URL parsing used by the API gateway."""

from backend.api.services.gateway import _normalize_service_url


def test_normalize_service_url_hostport_without_scheme():
    raw = "stocktrader-market-data-lyh3:10000"
    assert _normalize_service_url(raw, "http://localhost:8001") == "http://stocktrader-market-data-lyh3:10000"


def test_normalize_service_url_preserves_http_and_https():
    assert _normalize_service_url("http://svc:8000", "http://localhost:8001") == "http://svc:8000"
    assert _normalize_service_url("https://svc.example.com", "http://localhost:8001") == "https://svc.example.com"


def test_normalize_service_url_uses_fallback_when_blank():
    assert _normalize_service_url("", "http://localhost:8001") == "http://localhost:8001"
