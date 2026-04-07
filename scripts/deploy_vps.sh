#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  Deploy StockTrader to VPS
# ═══════════════════════════════════════════════════════════════════════
#
#  Prerequisites: Run bootstrap_server.sh first.
#
#  Usage:
#    bash scripts/deploy_vps.sh              # full deploy
#    bash scripts/deploy_vps.sh --rebuild    # force rebuild images
#    bash scripts/deploy_vps.sh --pull       # just pull & restart
#
# ═══════════════════════════════════════════════════════════════════════

set -euo pipefail

APP_DIR="/opt/stocktrader"
COMPOSE_FILE="docker-compose.services.yml"

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${BLUE}[deploy]${NC} $*"; }
ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*"; }

cd "$APP_DIR"

# ── Parse arguments ─────────────────────────────────────────────────
REBUILD=false
PULL_ONLY=false

for arg in "$@"; do
    case "$arg" in
        --rebuild) REBUILD=true ;;
        --pull)    PULL_ONLY=true ;;
    esac
done

# ── 1. Pull latest code ────────────────────────────────────────────
log "Pulling latest code..."
git fetch origin main
git reset --hard origin/main
ok "Code updated to $(git log --oneline -1)"

# ── 2. Check .env ──────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    err ".env file missing! Copy .env.example and configure it."
    exit 1
fi
ok ".env file found"

# ── Pull-only mode ─────────────────────────────────────────────────
if [ "$PULL_ONLY" = true ]; then
    log "Restarting services..."
    docker compose -f "$COMPOSE_FILE" restart
    ok "Services restarted"
    exit 0
fi

# ── 3. Build images ────────────────────────────────────────────────
if [ "$REBUILD" = true ]; then
    log "Force rebuilding all images..."
    docker compose -f "$COMPOSE_FILE" build --no-cache
else
    log "Building images (cached)..."
    docker compose -f "$COMPOSE_FILE" build
fi
ok "Images built"

# ── 4. Stop existing services ─────────────────────────────────────
log "Stopping existing services..."
docker compose -f "$COMPOSE_FILE" down --remove-orphans 2>/dev/null || true
ok "Old services stopped"

# ── 5. Start infrastructure first ─────────────────────────────────
log "Starting infrastructure (postgres, redis, rabbitmq)..."
docker compose -f "$COMPOSE_FILE" up -d postgres redis rabbitmq
log "Waiting for infrastructure to be healthy..."
sleep 10
ok "Infrastructure up"

# ── 6. Start monitoring ──────────────────────────────────────────
log "Starting monitoring (prometheus, grafana)..."
docker compose -f "$COMPOSE_FILE" up -d prometheus grafana
ok "Monitoring up"

# ── 7. Start all services ────────────────────────────────────────
log "Starting all application services..."
docker compose -f "$COMPOSE_FILE" up -d
ok "All services started"

# ── 8. Wait and verify ──────────────────────────────────────────
log "Waiting for services to initialize..."
sleep 15

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Deployment Complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""

# Health check
log "Running health checks..."
GATEWAY_HEALTH=$(curl -sf http://localhost:8000/health 2>/dev/null || echo '{"status":"unreachable"}')
echo "  Gateway health: $GATEWAY_HEALTH"

echo ""
echo "  Service URLs:"
echo "    API Gateway:    http://$(hostname -I | awk '{print $1}'):8000"
echo "    Frontend:       http://$(hostname -I | awk '{print $1}'):4200"
echo "    Grafana:        http://$(hostname -I | awk '{print $1}'):3000"
echo "    RabbitMQ UI:    http://$(hostname -I | awk '{print $1}'):15672"
echo "    Prometheus:     http://$(hostname -I | awk '{print $1}'):9090"
echo ""
echo "  Useful commands:"
echo "    docker compose -f $COMPOSE_FILE logs -f           # tail all logs"
echo "    docker compose -f $COMPOSE_FILE logs -f trading   # tail one service"
echo "    docker compose -f $COMPOSE_FILE ps                # service status"
echo "    docker compose -f $COMPOSE_FILE restart trading   # restart one"
echo ""
