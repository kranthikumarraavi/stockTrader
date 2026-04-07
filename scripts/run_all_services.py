#!/usr/bin/env python3
"""Start all StockTrader microservices locally with uvicorn.

Usage:
    python scripts/run_all_services.py              # stable mode
    python scripts/run_all_services.py --reload      # auto-reload
    python scripts/run_all_services.py --services gateway,market-data  # subset

All services run in parallel. Press Ctrl+C to stop.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# ── Service definitions ─────────────────────────────────────────────────────

@dataclass
class ServiceDef:
    name: str
    port: int
    dir_name: str        # Directory name under services/
    color: str           # ANSI color code for output


SERVICES: list[ServiceDef] = [
    ServiceDef("api-gateway",           8000, "api-gateway",                "\033[96m"),
    ServiceDef("market-data",           8001, "market-data-service",        "\033[92m"),
    ServiceDef("prediction",            8002, "prediction-service",         "\033[93m"),
    ServiceDef("trading",               8003, "trading-service",            "\033[94m"),
    ServiceDef("portfolio-risk",        8004, "portfolio-risk-service",     "\033[95m"),
    ServiceDef("backtest",              8005, "backtest-service",           "\033[91m"),
    ServiceDef("model-management",      8006, "model-management-service",   "\033[96m"),
    ServiceDef("execution",             8007, "execution-service",          "\033[92m"),
    ServiceDef("options-signal",        8008, "options-signal-service",     "\033[93m"),
    ServiceDef("intraday-features",     8009, "intraday-feature-service",   "\033[35m"),
    ServiceDef("intraday-prediction",   8010, "intraday-prediction-service","\033[35m"),
    ServiceDef("trade-supervisor",      8011, "trade-supervisor-service",   "\033[35m"),
]

RESET = "\033[0m"


def _find_python() -> str:
    """Find the best Python interpreter (prefer .venv)."""
    project_root = Path(__file__).resolve().parent.parent
    venv_python = project_root / ".venv" / ("Scripts" if os.name == "nt" else "bin") / (
        "python.exe" if os.name == "nt" else "python"
    )
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def _set_service_env_vars() -> dict[str, str]:
    """Build environment with service URLs for inter-service communication."""
    env = os.environ.copy()

    env["MARKET_DATA_URL"] = "http://localhost:8001"
    env["PREDICTION_URL"] = "http://localhost:8002"
    env["TRADING_URL"] = "http://localhost:8003"
    env["PORTFOLIO_RISK_URL"] = "http://localhost:8004"
    env["BACKTEST_URL"] = "http://localhost:8005"
    env["MODEL_MANAGEMENT_URL"] = "http://localhost:8006"
    env["EXECUTION_URL"] = "http://localhost:8007"
    env["OPTIONS_SIGNAL_URL"] = "http://localhost:8008"
    env["INTRADAY_FEATURE_URL"] = "http://localhost:8009"
    env["INTRADAY_PREDICTION_URL"] = "http://localhost:8010"
    env["TRADE_SUPERVISOR_URL"] = "http://localhost:8011"

    return env


def main():
    parser = argparse.ArgumentParser(description="Start StockTrader microservices")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    parser.add_argument(
        "--services",
        type=str,
        default=None,
        help="Comma-separated list of services to start (default: all)",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    python = _find_python()
    env = _set_service_env_vars()

    # Filter services if requested
    requested = SERVICES
    if args.services:
        names = {s.strip().lower() for s in args.services.split(",")}
        requested = [s for s in SERVICES if s.name in names]
        if not requested:
            print(f"No matching services found. Available: {', '.join(s.name for s in SERVICES)}")
            sys.exit(1)

    reload_args = ["--reload"] if args.reload else []

    print("\033[1m")
    print("═" * 60)
    print("  StockTrader Microservices Launcher")
    print("═" * 60)
    print(RESET)

    processes: list[tuple[ServiceDef, subprocess.Popen]] = []

    # Ensure project root is on PYTHONPATH so services can import backend.*
    env["PYTHONPATH"] = str(project_root) + os.pathsep + env.get("PYTHONPATH", "")

    for svc in requested:
        service_dir = project_root / "services" / svc.dir_name
        cmd = [
            python, "-m", "uvicorn",
            "app.main:app",
            "--host", "0.0.0.0",
            "--port", str(svc.port),
            "--app-dir", str(service_dir),
        ] + reload_args

        print(f"  {svc.color}▸{RESET} Starting {svc.name:25s} → http://localhost:{svc.port}")

        proc = subprocess.Popen(
            cmd,
            cwd=str(project_root),
            env=env,
            stdout=subprocess.DEVNULL if not args.reload else None,
            stderr=subprocess.DEVNULL if not args.reload else None,
        )
        processes.append((svc, proc))
        time.sleep(0.3)  # stagger startup slightly

    print()
    print("\033[1m" + "─" * 60 + RESET)
    print(f"  \033[92m✓ {len(processes)} services started\033[0m")
    print()
    print("  Service URLs:")
    for svc, _ in processes:
        print(f"    {svc.color}{svc.name:25s}{RESET} http://localhost:{svc.port}")
    print()
    print("  Infrastructure:")
    print(f"    {'PostgreSQL':25s} localhost:5432")
    print(f"    {'Redis':25s} localhost:6379")
    print(f"    {'RabbitMQ':25s} localhost:5672  (UI: 15672)")
    print(f"    {'Prometheus':25s} localhost:9090")
    print(f"    {'Grafana':25s} localhost:3000")
    print()
    print("  \033[93mPress Ctrl+C to stop all services\033[0m")
    print("\033[1m" + "─" * 60 + RESET)

    # Monitor processes
    def _shutdown(sig=None, frame=None):
        print("\n\033[93mShutting down all services...\033[0m")
        for svc, proc in processes:
            if proc.poll() is None:
                proc.terminate()
        for svc, proc in processes:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        print("\033[92mAll services stopped.\033[0m")
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    try:
        while True:
            for svc, proc in processes:
                if proc.poll() is not None:
                    print(f"\033[91m  ✗ {svc.name} exited with code {proc.returncode}\033[0m")
            time.sleep(2)
    except KeyboardInterrupt:
        _shutdown()


if __name__ == "__main__":
    main()
