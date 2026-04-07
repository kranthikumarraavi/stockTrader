#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  Bootstrap a fresh VPS (Ubuntu 22.04+) for StockTrader deployment
# ═══════════════════════════════════════════════════════════════════════
#
#  Usage:
#    curl -sSL https://raw.githubusercontent.com/magicmirror23/stockTraderV3/main/scripts/bootstrap_server.sh | bash
#    # or
#    bash scripts/bootstrap_server.sh
#
# ═══════════════════════════════════════════════════════════════════════

set -euo pipefail

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${BLUE}[bootstrap]${NC} $*"; }
ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }

# ── 1. System updates ──────────────────────────────────────────────────
log "Updating system packages..."
sudo apt-get update -qq
sudo apt-get upgrade -y -qq
ok "System updated"

# ── 2. Install Docker ──────────────────────────────────────────────────
if command -v docker &>/dev/null; then
    ok "Docker already installed: $(docker --version)"
else
    log "Installing Docker..."
    sudo apt-get install -y -qq ca-certificates curl gnupg lsb-release

    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    sudo apt-get update -qq
    sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    sudo usermod -aG docker "$USER"

    ok "Docker installed: $(docker --version)"
fi

# ── 3. Install Docker Compose (v2 plugin) ─────────────────────────────
if docker compose version &>/dev/null; then
    ok "Docker Compose already available: $(docker compose version)"
else
    log "Installing Docker Compose plugin..."
    sudo apt-get install -y -qq docker-compose-plugin
    ok "Docker Compose installed"
fi

# ── 4. Install Git ────────────────────────────────────────────────────
if ! command -v git &>/dev/null; then
    log "Installing Git..."
    sudo apt-get install -y -qq git
fi
ok "Git: $(git --version)"

# ── 5. Firewall ──────────────────────────────────────────────────────
log "Configuring firewall (ufw)..."
sudo apt-get install -y -qq ufw
sudo ufw --force reset
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw allow 8000/tcp  # API Gateway
sudo ufw allow 3000/tcp  # Grafana
sudo ufw --force enable
ok "Firewall configured"

# ── 6. Create application directory ──────────────────────────────────
APP_DIR="/opt/stocktrader"
log "Setting up application directory: $APP_DIR"
sudo mkdir -p "$APP_DIR"
sudo chown "$USER:$USER" "$APP_DIR"
ok "Application directory ready"

# ── 7. Clone repository ─────────────────────────────────────────────
if [ -d "$APP_DIR/.git" ]; then
    log "Repository already cloned. Pulling latest..."
    cd "$APP_DIR"
    git pull origin main
else
    log "Cloning repository..."
    git clone https://github.com/magicmirror23/stockTraderV3.git "$APP_DIR"
    cd "$APP_DIR"
fi
ok "Repository ready"

# ── 8. Create .env from example ─────────────────────────────────────
if [ ! -f "$APP_DIR/.env" ]; then
    if [ -f "$APP_DIR/.env.example" ]; then
        cp "$APP_DIR/.env.example" "$APP_DIR/.env"
        warn "Created .env from .env.example – EDIT WITH YOUR CREDENTIALS"
    fi
fi

# ── 9. Summary ──────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Server bootstrapped successfully!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""
echo "  Next steps:"
echo ""
echo "    1. Edit .env with your credentials:"
echo "       nano $APP_DIR/.env"
echo ""
echo "    2. Deploy the application:"
echo "       cd $APP_DIR"
echo "       bash scripts/deploy_vps.sh"
echo ""
echo "    3. Or start with Docker Compose directly:"
echo "       docker compose -f docker-compose.services.yml up -d"
echo ""
echo -e "  ${YELLOW}NOTE: Log out and back in for Docker group to take effect.${NC}"
echo ""
