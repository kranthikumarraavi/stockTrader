# StockTrader – Microservices Architecture

## Overview

StockTrader is an AI-powered trading platform running as a **true microservices architecture**. Each backend service is an independent FastAPI application with its own Dockerfile, configuration, and health endpoints.

---

## Architecture Diagram

```
                    ┌──────────────────────┐
                    │   Angular Frontend   │
                    │     (port 4200)      │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │    API Gateway       │
                    │     (port 8000)      │
                    └──┬──┬──┬──┬──┬──┬───┘
         ┌─────────────┘  │  │  │  │  └──────────────┐
         │      ┌─────────┘  │  │  └────────┐        │
         ▼      ▼            ▼  ▼           ▼        ▼
    ┌────────┬────────┬────────┬────────┬────────┬────────┐
    │Market  │Predict │Trading │Port-   │Back-   │Model   │
    │Data    │ion     │        │folio   │test    │Mgmt    │
    │:8001   │:8002   │:8003   │Risk    │:8005   │:8006   │
    │        │        │        │:8004   │        │        │
    └────────┴────────┴────────┴────────┴────────┴────────┘
    ┌────────┬────────┬────────┬────────┬────────┐
    │Execu-  │Options │Intra-  │Intra-  │Trade   │
    │tion    │Signal  │day     │day     │Super-  │
    │:8007   │:8008   │Feature │Predict │visor   │
    │        │        │:8009   │:8010   │:8011   │
    └────────┴────────┴────────┴────────┴────────┘
         │        │        │        │        │
    ┌────▼────────▼────────▼────────▼────────▼────┐
    │           RabbitMQ (async events)           │
    │              (port 5672)                     │
    └─────────────────────────────────────────────┘
    ┌─────────────┐  ┌──────────┐  ┌─────────────┐
    │ PostgreSQL  │  │  Redis   │  │ Prometheus  │
    │   :5432     │  │  :6379   │  │   :9090     │
    └─────────────┘  └──────────┘  └──────┬──────┘
                                          │
                                   ┌──────▼──────┐
                                   │   Grafana   │
                                   │    :3000    │
                                   └─────────────┘
```

---

## Service Port Map

| Service                  | Port | Description                           |
|--------------------------|------|---------------------------------------|
| **Frontend**             | 4200 | Angular SPA                           |
| **API Gateway**          | 8000 | Reverse proxy & routing               |
| **Market Data**          | 8001 | Market data ingestion & streaming     |
| **Prediction**           | 8002 | ML inference & regime detection       |
| **Trading**              | 8003 | Trade execution, bot, paper trading   |
| **Portfolio Risk**       | 8004 | Risk management & portfolio analytics |
| **Backtest**             | 8005 | Strategy backtesting                  |
| **Model Management**     | 8006 | Model retraining, drift, registry     |
| **Execution**            | 8007 | Micro-trade execution engine          |
| **Options Signal**       | 8008 | F&O signal generation                 |
| **Intraday Features**    | 8009 | Intraday feature computation          |
| **Intraday Prediction**  | 8010 | Intraday ML inference                 |
| **Trade Supervisor**     | 8011 | Intraday risk supervisor              |
| **PostgreSQL**           | 5432 | Primary database                      |
| **Redis**                | 6379 | Cache layer                           |
| **RabbitMQ**             | 5672 | Message broker (UI: 15672)            |
| **Prometheus**           | 9090 | Metrics collection                    |
| **Grafana**              | 3000 | Monitoring dashboards                 |

---

## Project Structure

```
├── services/                      # Microservice directories
│   ├── api-gateway/               # Port 8000 – reverse proxy
│   ├── market-data-service/       # Port 8001 – market data
│   ├── prediction-service/        # Port 8002 – ML inference
│   ├── trading-service/           # Port 8003 – trade execution
│   ├── portfolio-risk-service/    # Port 8004 – risk management
│   ├── backtest-service/          # Port 8005 – backtesting
│   ├── model-management-service/  # Port 8006 – model lifecycle
│   ├── execution-service/         # Port 8007 – execution engine
│   ├── options-signal-service/    # Port 8008 – options signals
│   ├── intraday-feature-service/  # Port 8009 – intraday features
│   ├── intraday-prediction-service/ # Port 8010 – intraday ML
│   └── trade-supervisor-service/  # Port 8011 – trade supervisor
│
├── packages/                      # Shared libraries
│   ├── common-config/             # Unified configuration
│   ├── common-logging/            # Structured logging
│   ├── common-utils/              # Health endpoints, events, retry
│   ├── common-types/              # Shared Pydantic types
│   └── common-db/                 # Database session & models
│
├── backend/                       # Core business logic (shared)
│   ├── api/routers/               # FastAPI route handlers
│   ├── api/services/              # Service entry points
│   ├── services/                  # Business logic layer
│   ├── prediction_engine/         # ML training & inference
│   ├── trading_engine/            # Broker adapters
│   ├── market_data_service/       # Data providers
│   ├── intraday/                  # Intraday modules
│   ├── ml_platform/               # ML pipeline
│   ├── paper_trading/             # Paper trading engine
│   └── db/                        # Database models
│
├── frontend/                      # Angular SPA
│
├── infra/                         # Infrastructure config
│   ├── docker/                    # Dockerfiles, nginx
│   ├── prometheus/                # Prometheus scrape config
│   └── grafana/                   # Dashboards & provisioning
│
├── scripts/                       # Operations scripts
│   ├── run_all_services.py        # Start all services locally
│   ├── bootstrap_server.sh        # VPS initial setup
│   └── deploy_vps.sh             # Deploy to VPS
│
├── docker-compose.services.yml    # Full microservices compose
├── .env.microservices.example     # Environment template
└── models/                        # Model artifacts
```

Each service directory contains:
```
services/<service-name>/
├── Dockerfile              # Independent container image
├── requirements.txt        # Service-specific dependencies
└── app/
    ├── __init__.py
    ├── main.py             # FastAPI app + router wiring
    └── config.py           # Service configuration
```

---

## Running Locally

### Option 1: Python Script (No Docker)

Start all 12 services with one command:

```bash
python scripts/run_all_services.py
```

Options:
```bash
python scripts/run_all_services.py --reload              # auto-reload on changes
python scripts/run_all_services.py --services gateway,market-data  # subset
```

Prerequisites:
- Python 3.11+ with venv at `.venv/`
- `pip install -r requirements.txt`
- PostgreSQL and Redis running (optional for basic dev)

### Option 2: Docker Compose (Full Stack)

```bash
# Start everything: all services + infra + monitoring
docker compose -f docker-compose.services.yml up -d

# Start only specific services
docker compose -f docker-compose.services.yml up -d api-gateway market-data prediction

# View logs
docker compose -f docker-compose.services.yml logs -f trading

# Restart a service
docker compose -f docker-compose.services.yml restart prediction

# Stop everything
docker compose -f docker-compose.services.yml down
```

### Option 3: Legacy Mode (Original Scripts)

The original start scripts still work for backward compatibility:

```powershell
# Windows
$env:PREDICTION_NO_TRADE_BAND_SCALE = "0.25"
powershell -ExecutionPolicy Bypass -File .\scripts\start_services.ps1

# Linux/Mac
bash scripts/start_services.sh
```

---

## VPS Deployment (Oracle Cloud / Linux Server)

### Initial Setup

```bash
# On a fresh Ubuntu 22.04+ VPS:
bash scripts/bootstrap_server.sh
```

This installs Docker, Git, configures the firewall, and clones the repo.

### Deploy

```bash
# Edit .env with credentials
nano /opt/stocktrader/.env

# Deploy
bash scripts/deploy_vps.sh

# Force rebuild
bash scripts/deploy_vps.sh --rebuild

# Quick update (pull + restart)
bash scripts/deploy_vps.sh --pull
```

---

## Health Endpoints

Every service exposes:

| Endpoint      | Purpose           | Example Response                                |
|---------------|-------------------|-------------------------------------------------|
| `/health`     | Liveness check    | `{"status": "ok", "service": "prediction"}`     |
| `/ready`      | Readiness check   | `{"service": "prediction", "ready": true}`      |
| `/status`     | Service status    | `{"service": "prediction", "uptime_seconds": 123}` |
| `/metrics`    | Prometheus metrics| Prometheus text format                          |

All endpoints also available under `/api/v1/` prefix.

Gateway aggregated health: `GET /api/v1/health/services`

---

## Service Communication

### Synchronous (HTTP)

All client requests flow through the **API Gateway** (port 8000), which proxies to the appropriate downstream service:

```
Client → Gateway:8000 → market-data:8001
                      → prediction:8002
                      → trading:8003
                      → etc.
```

### Asynchronous (RabbitMQ)

Services publish domain events to the `stocktrader.events` topic exchange:

| Event                   | Producer        | Consumers                    |
|-------------------------|-----------------|------------------------------|
| `market_data_updated`   | Market Data     | Prediction, Trading          |
| `model_trained`         | Model Management| Prediction                   |
| `prediction_generated`  | Prediction      | Trading, Execution           |
| `trade_signal_created`  | Trading         | Execution, Trade Supervisor  |
| `trade_executed`        | Execution       | Portfolio Risk, Trading      |

---

## Monitoring

### Prometheus

Scrapes `/metrics` from all 12 services every 15 seconds. Configuration at `infra/prometheus/prometheus.yml`.

### Grafana

Pre-configured dashboards at `infra/grafana/dashboards/`:

- **Service Dashboard**: Health overview, request rates, latency p95, error rates
- Panels for: prediction latency, trade execution latency, risk events

Access: `http://localhost:3000` (admin/admin)

---

## Configuration

All services read from a single `.env` file:

```bash
# Copy the template
cp .env.microservices.example .env

# Edit with your values
$EDITOR .env
```

Key variables:

| Variable               | Description                           | Default                              |
|------------------------|---------------------------------------|--------------------------------------|
| `DATABASE_URL`         | PostgreSQL connection string          | `sqlite:///stocktrader.db`           |
| `REDIS_URL`            | Redis connection string               | `redis://localhost:6379/0`           |
| `RABBITMQ_URL`         | RabbitMQ connection string            | `amqp://guest:guest@localhost:5672/` |
| `LOG_LEVEL`            | Logging level                         | `INFO`                               |
| `ALLOWED_ORIGINS`      | CORS origins (comma-separated)        | `http://localhost:4200`              |
| `ANGEL_API_KEY`        | Angel One API key                     | (required for live trading)          |
| `MARKET_DATA_URL`      | Market Data service URL               | `http://localhost:8001`              |
| `PREDICTION_URL`       | Prediction service URL                | `http://localhost:8002`              |

See `.env.microservices.example` for the complete list.

---

## Shared Packages

| Package          | Purpose                                    |
|------------------|--------------------------------------------|
| `common-config`  | Pydantic settings with env var loading      |
| `common-logging` | Structured logging (console + rotating file)|
| `common-utils`   | Health endpoints, RabbitMQ events, retry    |
| `common-types`   | Shared Pydantic request/response models     |
| `common-db`      | SQLAlchemy session factory and ORM models   |

Install for local development:
```bash
pip install -e packages/common-config
pip install -e packages/common-logging
pip install -e packages/common-utils
pip install -e packages/common-types
pip install -e packages/common-db
```
