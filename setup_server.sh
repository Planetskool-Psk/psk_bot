#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# PSK Bot — Full Server Setup Script
# One-command production deployment for Ubuntu/Debian
# Target: 2-core, 12GB RAM, AMD Milan VM
# Domain: chatbot.planetskool.com
# ═══════════════════════════════════════════════════════════════════════════════
#
# Usage:
#   # Clone your repo onto the server first, then run:
#   cd /opt/psk-bot
#   sudo bash setup_server.sh
#
#   # Or pipe from a fresh server:
#   sudo bash setup_server.sh --git-repo https://github.com/youruser/psk-bot.git
#
# What this script does:
#   1.  System dependencies & OS hardening
#   2.  Swap file (if RAM < 16GB)
#   3.  Install Ollama + pull gemma3:1b & nomic-embed-text
#   4.  Python 3 venv + project dependencies
#   5.  Generate secure .env config
#   6.  systemd services (psk-bot + ollama override)
#   7.  Nginx reverse proxy for chatbot.planetskool.com
#   8.  SSL certificate via Let's Encrypt (certbot)
#   9.  UFW firewall (SSH + HTTP + HTTPS only)
#  10.  Log rotation
#  11.  Post-deploy health checks
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# Configuration — edit these if needed
# ─────────────────────────────────────────────────────────────────────────────
DOMAIN="chatbot.planetskool.com"
APP_DIR="/opt/psk-bot"
SERVICE_NAME="psk-bot"
SERVICE_USER="pskbot"
PYTHON_VERSION="3"                # Will use python3
VENV_DIR="${APP_DIR}/venv"
PORT="5173"
GIT_REPO=""                       # Set via --git-repo flag or leave empty
SKIP_SSL="false"                  # Set via --skip-ssl flag
CERTBOT_EMAIL=""                  # Set via --email flag; required for SSL
SKIP_FIREWALL="false"             # Set via --skip-firewall flag

# Ollama models
LLM_MODEL="gemma3:1b"
EMBEDDING_MODEL="nomic-embed-text"

# ─────────────────────────────────────────────────────────────────────────────
# Parse CLI arguments
# ─────────────────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --git-repo)      GIT_REPO="$2";       shift 2 ;;
        --domain)        DOMAIN="$2";          shift 2 ;;
        --app-dir)       APP_DIR="$2";         shift 2 ;;
        --email)         CERTBOT_EMAIL="$2";   shift 2 ;;
        --port)          PORT="$2";            shift 2 ;;
        --skip-ssl)      SKIP_SSL="true";      shift   ;;
        --skip-firewall) SKIP_FIREWALL="true"; shift   ;;
        --help|-h)
            echo "Usage: sudo bash setup_server.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --git-repo URL     Clone project from this Git URL into --app-dir"
            echo "  --domain DOMAIN    Domain name (default: chatbot.planetskool.com)"
            echo "  --app-dir PATH     Install directory (default: /opt/psk-bot)"
            echo "  --email EMAIL      Email for Let's Encrypt certificate"
            echo "  --port PORT        App port (default: 5173)"
            echo "  --skip-ssl         Skip SSL certificate setup"
            echo "  --skip-firewall    Skip UFW firewall configuration"
            echo "  -h, --help         Show this help"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Update VENV_DIR if APP_DIR was changed
VENV_DIR="${APP_DIR}/venv"

# ─────────────────────────────────────────────────────────────────────────────
# Colors & helpers
# ─────────────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

step_num=0
total_steps=11

step() {
    step_num=$((step_num + 1))
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}[${step_num}/${total_steps}] $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

info()    { echo -e "  ${CYAN}ℹ${NC}  $1"; }
success() { echo -e "  ${GREEN}✔${NC}  $1"; }
warn()    { echo -e "  ${YELLOW}⚠${NC}  $1"; }
fail()    { echo -e "  ${RED}✘${NC}  $1"; exit 1; }

# ─────────────────────────────────────────────────────────────────────────────
# Pre-flight checks
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║          PSK Bot — Full Server Setup                    ║${NC}"
echo -e "${BOLD}${CYAN}║          Domain: ${DOMAIN}              ║${NC}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# Must be root
if [[ $EUID -ne 0 ]]; then
    fail "This script must be run as root (use sudo)"
fi

# Check OS
if [[ ! -f /etc/os-release ]]; then
    fail "Cannot detect OS. This script supports Ubuntu/Debian only."
fi
source /etc/os-release
if [[ "$ID" != "ubuntu" && "$ID" != "debian" ]]; then
    warn "Detected $ID — this script is tested on Ubuntu/Debian. Proceeding anyway..."
fi
info "OS: ${PRETTY_NAME}"

# Check hardware
CPU_CORES=$(nproc)
TOTAL_RAM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
TOTAL_RAM_GB=$(awk "BEGIN {printf \"%.1f\", ${TOTAL_RAM_MB}/1024}")
info "CPU: ${CPU_CORES} cores | RAM: ${TOTAL_RAM_GB} GB"

if [[ $TOTAL_RAM_MB -lt 6000 ]]; then
    warn "Low RAM detected (${TOTAL_RAM_GB}GB). Minimum recommended is 8GB."
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1: System dependencies
# ═══════════════════════════════════════════════════════════════════════════════
step "Installing system dependencies"

export DEBIAN_FRONTEND=noninteractive

apt-get update -qq
apt-get install -y -qq \
    python3 python3-pip python3-venv python3-dev \
    nginx certbot python3-certbot-nginx \
    curl wget git build-essential \
    ufw logrotate \
    jq htop unzip \
    2>&1 | tail -1

success "System packages installed"

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2: OS tuning & swap
# ═══════════════════════════════════════════════════════════════════════════════
step "OS tuning & swap setup"

# Sysctl tuning for a web server
cat > /etc/sysctl.d/99-psk-bot.conf <<'SYSCTL'
# PSK Bot — kernel tuning for 2-core web/LLM server
net.core.somaxconn = 512
net.ipv4.tcp_max_syn_backlog = 512
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_fin_timeout = 15
net.ipv4.ip_local_port_range = 10000 65535
# Reduce swappiness — prefer keeping app in RAM
vm.swappiness = 10
vm.dirty_ratio = 15
vm.dirty_background_ratio = 5
# File descriptor limits
fs.file-max = 131072
SYSCTL
sysctl -p /etc/sysctl.d/99-psk-bot.conf > /dev/null 2>&1
success "Kernel parameters tuned"

# Create swap if RAM < 16GB and no swap exists
SWAP_TOTAL=$(awk '/SwapTotal/ {print $2}' /proc/meminfo)
if [[ $SWAP_TOTAL -lt 1048576 && $TOTAL_RAM_MB -lt 16000 ]]; then
    SWAP_SIZE="4G"
    info "Creating ${SWAP_SIZE} swap file (RAM is ${TOTAL_RAM_GB}GB)..."
    if [[ ! -f /swapfile ]]; then
        fallocate -l ${SWAP_SIZE} /swapfile
        chmod 600 /swapfile
        mkswap /swapfile > /dev/null
        swapon /swapfile
        echo "/swapfile none swap sw 0 0" >> /etc/fstab
        success "Swap file created (${SWAP_SIZE})"
    else
        success "Swap file already exists"
    fi
else
    success "Swap OK (${SWAP_TOTAL}KB)"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3: Create service user
# ═══════════════════════════════════════════════════════════════════════════════
step "Creating service user"

if id "${SERVICE_USER}" &>/dev/null; then
    success "User '${SERVICE_USER}' already exists"
else
    useradd --system --shell /usr/sbin/nologin --home-dir "${APP_DIR}" --create-home "${SERVICE_USER}"
    success "Created system user '${SERVICE_USER}'"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4: Install Ollama
# ═══════════════════════════════════════════════════════════════════════════════
step "Installing Ollama & pulling models"

if command -v ollama &>/dev/null; then
    info "Ollama already installed, checking for updates..."
    curl -fsSL https://ollama.com/install.sh | sh 2>&1 | tail -3
else
    info "Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh 2>&1 | tail -3
fi
success "Ollama installed"

# Configure Ollama for constrained VM
mkdir -p /etc/systemd/system/ollama.service.d
cat > /etc/systemd/system/ollama.service.d/override.conf <<EOF
[Service]
Environment="OLLAMA_HOST=127.0.0.1:11434"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_KEEP_ALIVE=30m"
Environment="OLLAMA_MAX_QUEUE=4"
Environment="OLLAMA_ORIGINS=*"
# Cap Ollama memory at 4GB — leaves room for Python + OS
MemoryMax=4G
LimitNOFILE=65536
EOF

systemctl daemon-reload
systemctl enable ollama
systemctl restart ollama
success "Ollama service configured"

# Wait for Ollama to be ready
info "Waiting for Ollama to start..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:11434/api/version > /dev/null 2>&1; then
        break
    fi
    sleep 1
done

if ! curl -sf http://localhost:11434/api/version > /dev/null 2>&1; then
    fail "Ollama did not start within 30 seconds"
fi
OLLAMA_VERSION=$(curl -sf http://localhost:11434/api/version | jq -r '.version // "unknown"')
success "Ollama running (v${OLLAMA_VERSION})"

# Pull the LLM model
info "Pulling ${LLM_MODEL} (this may take a few minutes on first run)..."
ollama pull "${LLM_MODEL}" 2>&1 | tail -1
success "Model ${LLM_MODEL} ready"

# Pull the embedding model
info "Pulling ${EMBEDDING_MODEL}..."
ollama pull "${EMBEDDING_MODEL}" 2>&1 | tail -1
success "Model ${EMBEDDING_MODEL} ready"

# Pre-warm the LLM so first request is fast
info "Pre-warming ${LLM_MODEL}..."
ollama run "${LLM_MODEL}" "hi" > /dev/null 2>&1 || true
success "Model pre-warmed"

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 5: Project setup
# ═══════════════════════════════════════════════════════════════════════════════
step "Setting up PSK Bot project"

# Clone from git if requested, otherwise expect files in APP_DIR
if [[ -n "$GIT_REPO" ]]; then
    if [[ -d "${APP_DIR}/.git" ]]; then
        info "Repo already cloned, pulling latest..."
        cd "${APP_DIR}" && git pull --ff-only
    else
        info "Cloning from ${GIT_REPO}..."
        git clone "${GIT_REPO}" "${APP_DIR}"
    fi
    success "Project cloned to ${APP_DIR}"
else
    if [[ ! -f "${APP_DIR}/run.py" ]]; then
        # We're probably running from inside the project dir
        SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        if [[ -f "${SCRIPT_DIR}/run.py" ]]; then
            if [[ "${SCRIPT_DIR}" != "${APP_DIR}" ]]; then
                info "Copying project from ${SCRIPT_DIR} to ${APP_DIR}..."
                mkdir -p "${APP_DIR}"
                rsync -a --exclude='venv' --exclude='.git' --exclude='__pycache__' \
                    "${SCRIPT_DIR}/" "${APP_DIR}/"
                success "Project copied to ${APP_DIR}"
            else
                success "Project already at ${APP_DIR}"
            fi
        else
            fail "run.py not found. Either run from project dir or use --git-repo"
        fi
    else
        success "Project found at ${APP_DIR}"
    fi
fi

# Ensure required directories exist
mkdir -p "${APP_DIR}/data/documents"
mkdir -p "${APP_DIR}/vector_store"
mkdir -p "${APP_DIR}/logs"

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 6: Python virtual environment & dependencies
# ═══════════════════════════════════════════════════════════════════════════════
step "Setting up Python environment"

cd "${APP_DIR}"

if [[ ! -d "${VENV_DIR}" ]]; then
    info "Creating Python virtual environment..."
    python3 -m venv "${VENV_DIR}"
fi
source "${VENV_DIR}/bin/activate"

info "Upgrading pip..."
pip install --upgrade pip setuptools wheel -q

info "Installing project dependencies..."
pip install -r "${APP_DIR}/requirements.txt" -q

PYTHON_VERSION_FULL=$("${VENV_DIR}/bin/python3" --version 2>&1)
success "Virtual environment ready (${PYTHON_VERSION_FULL})"

# Verify critical imports
"${VENV_DIR}/bin/python3" -c "
import flask, flask_socketio, flask_cors, ollama, faiss, sentence_transformers
print('All critical packages verified')
" 2>&1 | while read -r line; do info "$line"; done

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 7: Generate .env configuration
# ═══════════════════════════════════════════════════════════════════════════════
step "Generating environment configuration"

API_KEY=$(openssl rand -hex 32)
SECRET_KEY=$(openssl rand -hex 32)

if [[ -f "${APP_DIR}/.env" ]]; then
    cp "${APP_DIR}/.env" "${APP_DIR}/.env.backup.$(date +%Y%m%d%H%M%S)"
    warn "Existing .env backed up. Regenerating..."
fi

cat > "${APP_DIR}/.env" <<ENVEOF
# ═══════════════════════════════════════════════════════════════
# PSK Bot — Production Configuration
# Generated: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
# Server: ${CPU_CORES}-core / ${TOTAL_RAM_GB}GB RAM
# ═══════════════════════════════════════════════════════════════

# ─── Core ─────────────────────────────────────────────────────
DEBUG=false
PORT=${PORT}
OPTIMIZED_MODE=true
SECRET_KEY=${SECRET_KEY}

# ─── Ollama ───────────────────────────────────────────────────
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=${LLM_MODEL}
OLLAMA_KEEP_ALIVE=30m

# ─── LLM Generation — tuned for ${CPU_CORES}-core CPU ────────
LLM_NUM_PREDICT=384
LLM_NUM_CTX=2048
LLM_NUM_THREAD=${CPU_CORES}
LLM_NUM_BATCH=256
LLM_TEMPERATURE=0.4
LLM_TOP_P=0.85
LLM_TOP_K=30
LLM_TIMEOUT=120

# ─── Embeddings ──────────────────────────────────────────────
EMBEDDING_MODEL_NAME=nomic-embed-text

# ─── RAG ─────────────────────────────────────────────────────
CHUNK_SIZE=512
CHUNK_OVERLAP=100
TOP_K_RESULTS=5
CONTEXT_DOCUMENTS=5
CONTEXT_CHAR_LIMIT=3000

# ─── Conversation ───────────────────────────────────────────
MAX_CONVERSATION_HISTORY=6
PROMPT_HISTORY_TURNS=3

# ─── Web Search ─────────────────────────────────────────────
WEB_SEARCH_ENABLED=true
WEB_SEARCH_MAX_RESULTS=3
WEB_SEARCH_TIMEOUT=8

# ─── Robot API Security ─────────────────────────────────────
# This key is required for /api/v1/* endpoints
PSK_API_KEY=${API_KEY}
API_RATE_LIMIT=30

# ─── Vector Store ───────────────────────────────────────────
VECTOR_STORE_INDEX_NAME=faiss_index

# ─── Threading (match CPU cores) ────────────────────────────
OMP_NUM_THREADS=${CPU_CORES}
MKL_NUM_THREADS=${CPU_CORES}
NUMEXPR_NUM_THREADS=${CPU_CORES}
OPENBLAS_NUM_THREADS=${CPU_CORES}
TOKENIZERS_PARALLELISM=false

# ─── Python Optimizations ───────────────────────────────────
PYTHONOPTIMIZE=1
PYTHONDONTWRITEBYTECODE=1
ENVEOF

chmod 600 "${APP_DIR}/.env"
success ".env generated with secure API key"
info "API Key: ${API_KEY}"
info "Save this key — you'll need it for robot API calls"

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 8: systemd service
# ═══════════════════════════════════════════════════════════════════════════════
step "Creating systemd service"

cat > /etc/systemd/system/${SERVICE_NAME}.service <<EOF
[Unit]
Description=PSK Bot — AI Chat Assistant
Documentation=https://chatbot.planetskool.com/docs/
After=network-online.target ollama.service
Wants=ollama.service
Requires=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
Environment="PATH=${VENV_DIR}/bin:/usr/local/bin:/usr/bin:/bin"

# Start with gunicorn for production (gevent + WebSocket support)
ExecStart=${VENV_DIR}/bin/python run.py

# Graceful shutdown
ExecStop=/bin/kill -SIGTERM \$MAINPID
TimeoutStopSec=15

# Restart policy
Restart=always
RestartSec=5
StartLimitIntervalSec=300
StartLimitBurst=5

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

# Security hardening
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=${APP_DIR}/data ${APP_DIR}/vector_store ${APP_DIR}/logs
ReadOnlyPaths=${APP_DIR}

# Resource limits — leave room for Ollama (~4GB) + OS (~2GB)
MemoryMax=5G
CPUQuota=$((CPU_CORES * 90))%
LimitNOFILE=65536
LimitNPROC=4096

[Install]
WantedBy=multi-user.target
EOF

# Set ownership
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}"

systemctl daemon-reload
systemctl enable ${SERVICE_NAME}
success "Service '${SERVICE_NAME}' created and enabled"

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 9: Nginx reverse proxy
# ═══════════════════════════════════════════════════════════════════════════════
step "Configuring Nginx for ${DOMAIN}"

cat > /etc/nginx/sites-available/${SERVICE_NAME} <<'NGINXEOF'
# ═══════════════════════════════════════════════════════════════════════
# PSK Bot — Nginx Reverse Proxy
# Domain: chatbot.planetskool.com
# ═══════════════════════════════════════════════════════════════════════

# Rate limiting zones
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=general_limit:10m rate=30r/s;

upstream psk_backend {
    server 127.0.0.1:__PORT__;
    keepalive 16;
}

# ─── Redirect HTTP → HTTPS ───────────────────────────────────────────
server {
    listen 80;
    listen [::]:80;
    server_name __DOMAIN__;

    # Let's Encrypt challenge
    location /.well-known/acme-challenge/ {
        root /var/www/html;
        allow all;
    }

    # Redirect everything else to HTTPS
    location / {
        return 301 https://$host$request_uri;
    }
}

# ─── Main HTTPS server ───────────────────────────────────────────────
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name __DOMAIN__;

    # SSL will be configured by certbot — placeholder until then
    # ssl_certificate     /etc/letsencrypt/live/__DOMAIN__/fullchain.pem;
    # ssl_certificate_key /etc/letsencrypt/live/__DOMAIN__/privkey.pem;

    # ─── SSL hardening ───────────────────────────────────────
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:10m;
    ssl_session_tickets off;
    ssl_stapling on;
    ssl_stapling_verify on;

    # ─── Security headers ────────────────────────────────────
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;

    # ─── General settings ────────────────────────────────────
    client_max_body_size 50M;
    proxy_connect_timeout 10s;
    proxy_send_timeout 30s;

    # ─── Gzip compression ────────────────────────────────────
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 4;
    gzip_min_length 256;
    gzip_types
        application/json
        text/event-stream
        text/plain
        text/css
        text/javascript
        application/javascript
        application/xml
        image/svg+xml;

    # ─── Robot API endpoints (low latency) ───────────────────
    location /api/v1/ {
        limit_req zone=api_limit burst=20 nodelay;

        proxy_pass http://psk_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";

        # SSE streaming support — no buffering
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 120s;
        chunked_transfer_encoding on;

        # CORS for robot hardware
        add_header Access-Control-Allow-Origin "*" always;
        add_header Access-Control-Allow-Methods "GET, POST, OPTIONS" always;
        add_header Access-Control-Allow-Headers "Content-Type, X-API-Key, X-Client-ID, Authorization" always;
        add_header Access-Control-Max-Age 86400 always;

        if ($request_method = OPTIONS) {
            return 204;
        }
    }

    # ─── WebSocket (Socket.IO) ───────────────────────────────
    location /socket.io/ {
        proxy_pass http://psk_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_read_timeout 300s;
    }

    # ─── Swagger API docs ────────────────────────────────────
    location /docs/ {
        limit_req zone=general_limit burst=10 nodelay;

        proxy_pass http://psk_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
    }

    # ─── Static files (cache aggressively) ───────────────────
    location /static/ {
        proxy_pass http://psk_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_cache_valid 200 1d;
        expires 1d;
        add_header Cache-Control "public, immutable";
    }

    # ─── Admin panel ─────────────────────────────────────────
    location /admin/ {
        # Restrict admin access to internal networks (adjust as needed)
        # allow 10.0.0.0/8;
        # allow 172.16.0.0/12;
        # allow 192.168.0.0/16;
        # deny all;

        limit_req zone=general_limit burst=5 nodelay;

        proxy_pass http://psk_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
    }

    # ─── Web UI & remaining routes ───────────────────────────
    location / {
        limit_req zone=general_limit burst=10 nodelay;

        proxy_pass http://psk_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";

        # SSE support for /api/stream
        proxy_buffering off;
    }

    # ─── Block dot files ─────────────────────────────────────
    location ~ /\. {
        deny all;
        access_log off;
        log_not_found off;
    }
}
NGINXEOF

# Replace placeholders
sed -i "s/__DOMAIN__/${DOMAIN}/g" /etc/nginx/sites-available/${SERVICE_NAME}
sed -i "s/__PORT__/${PORT}/g"     /etc/nginx/sites-available/${SERVICE_NAME}

# Enable the site
ln -sf /etc/nginx/sites-available/${SERVICE_NAME} /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

# For initial setup without SSL, temporarily enable the HTTP block to serve directly
# We'll comment out the HTTPS block until certbot runs
if [[ "$SKIP_SSL" == "true" ]]; then
    # Replace the HTTP→HTTPS redirect with a direct proxy config
    cat > /etc/nginx/sites-available/${SERVICE_NAME} <<HTTPEOF
# PSK Bot — Nginx (HTTP only, no SSL)
limit_req_zone \$binary_remote_addr zone=api_limit:10m rate=10r/s;
limit_req_zone \$binary_remote_addr zone=general_limit:10m rate=30r/s;

upstream psk_backend {
    server 127.0.0.1:${PORT};
    keepalive 16;
}

server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    client_max_body_size 50M;
    proxy_connect_timeout 10s;
    proxy_send_timeout 30s;

    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 4;
    gzip_min_length 256;
    gzip_types application/json text/event-stream text/plain text/css application/javascript;

    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    location /api/v1/ {
        limit_req zone=api_limit burst=20 nodelay;
        proxy_pass http://psk_backend;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 120s;
        chunked_transfer_encoding on;
        add_header Access-Control-Allow-Origin "*" always;
        add_header Access-Control-Allow-Methods "GET, POST, OPTIONS" always;
        add_header Access-Control-Allow-Headers "Content-Type, X-API-Key, X-Client-ID, Authorization" always;
        if (\$request_method = OPTIONS) { return 204; }
    }

    location /socket.io/ {
        proxy_pass http://psk_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_buffering off;
        proxy_read_timeout 300s;
    }

    location / {
        limit_req zone=general_limit burst=10 nodelay;
        proxy_pass http://psk_backend;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Connection "";
        proxy_buffering off;
    }

    location ~ /\. { deny all; access_log off; log_not_found off; }
}
HTTPEOF
    info "SSL skipped — Nginx configured for HTTP only"
fi

# Test Nginx config
nginx -t 2>&1 | while read -r line; do info "$line"; done
systemctl enable nginx
systemctl restart nginx
success "Nginx configured for ${DOMAIN}"

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 10: SSL certificate (Let's Encrypt)
# ═══════════════════════════════════════════════════════════════════════════════
step "SSL certificate setup"

if [[ "$SKIP_SSL" == "true" ]]; then
    warn "SSL setup skipped (--skip-ssl flag). Run later with:"
    info "  sudo certbot --nginx -d ${DOMAIN}"
else
    # Check if domain resolves to this server
    SERVER_IP=$(curl -sf https://api.ipify.org || echo "unknown")
    DOMAIN_IP=$(dig +short "${DOMAIN}" 2>/dev/null | head -1 || echo "unresolved")

    if [[ "$DOMAIN_IP" == "unresolved" || "$DOMAIN_IP" == "" ]]; then
        warn "Domain ${DOMAIN} does not resolve yet."
        warn "Point your DNS A record to ${SERVER_IP} first, then run:"
        info "  sudo certbot --nginx -d ${DOMAIN}"

        # Fall back to HTTP-only config
        cat > /etc/nginx/sites-available/${SERVICE_NAME} <<HTTPFALLBACK
limit_req_zone \$binary_remote_addr zone=api_limit:10m rate=10r/s;
limit_req_zone \$binary_remote_addr zone=general_limit:10m rate=30r/s;

upstream psk_backend {
    server 127.0.0.1:${PORT};
    keepalive 16;
}

server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN} _;

    client_max_body_size 50M;
    gzip on;
    gzip_types application/json text/event-stream text/plain;

    location /.well-known/acme-challenge/ { root /var/www/html; allow all; }

    location /api/v1/ {
        limit_req zone=api_limit burst=20 nodelay;
        proxy_pass http://psk_backend;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 120s;
        add_header Access-Control-Allow-Origin "*" always;
        add_header Access-Control-Allow-Methods "GET, POST, OPTIONS" always;
        add_header Access-Control-Allow-Headers "Content-Type, X-API-Key, X-Client-ID" always;
        if (\$request_method = OPTIONS) { return 204; }
    }

    location /socket.io/ {
        proxy_pass http://psk_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_buffering off;
        proxy_read_timeout 300s;
    }

    location / {
        limit_req zone=general_limit burst=10 nodelay;
        proxy_pass http://psk_backend;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Connection "";
        proxy_buffering off;
    }

    location ~ /\. { deny all; }
}
HTTPFALLBACK
        nginx -t > /dev/null 2>&1 && systemctl reload nginx
    else
        info "Domain resolves to ${DOMAIN_IP}, server IP is ${SERVER_IP}"

        CERTBOT_FLAGS="--nginx -d ${DOMAIN} --non-interactive --agree-tos"
        if [[ -n "$CERTBOT_EMAIL" ]]; then
            CERTBOT_FLAGS="${CERTBOT_FLAGS} --email ${CERTBOT_EMAIL}"
        else
            CERTBOT_FLAGS="${CERTBOT_FLAGS} --register-unsafely-without-email"
            warn "No email provided — registering without email (use --email for recovery)"
        fi

        certbot ${CERTBOT_FLAGS} 2>&1 | tail -5
        success "SSL certificate installed for ${DOMAIN}"

        # Set up auto-renewal
        systemctl enable certbot.timer 2>/dev/null || true
        systemctl start certbot.timer 2>/dev/null || true
        info "SSL auto-renewal enabled"
    fi
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 11: Firewall & log rotation
# ═══════════════════════════════════════════════════════════════════════════════
step "Firewall & log rotation"

# ─── UFW Firewall ────────────────────────────────────────────────────
if [[ "$SKIP_FIREWALL" == "true" ]]; then
    warn "Firewall setup skipped (--skip-firewall flag)"
else
    info "Configuring UFW firewall..."
    ufw --force reset > /dev/null 2>&1
    ufw default deny incoming > /dev/null 2>&1
    ufw default allow outgoing > /dev/null 2>&1
    ufw allow ssh > /dev/null 2>&1
    ufw allow 'Nginx Full' > /dev/null 2>&1
    # Allow Ollama only from localhost (already default, but explicit)
    ufw deny 11434 > /dev/null 2>&1
    ufw --force enable > /dev/null 2>&1
    success "Firewall enabled (SSH + HTTP + HTTPS only)"
fi

# ─── Log Rotation ────────────────────────────────────────────────────
cat > /etc/logrotate.d/${SERVICE_NAME} <<LOGEOF
/var/log/${SERVICE_NAME}/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0640 ${SERVICE_USER} ${SERVICE_USER}
    sharedscripts
    postrotate
        systemctl reload ${SERVICE_NAME} > /dev/null 2>&1 || true
    endscript
}
LOGEOF

# Also ensure journald doesn't grow too large
mkdir -p /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/psk-bot.conf <<JDEOF
[Journal]
SystemMaxUse=500M
SystemMaxFileSize=50M
MaxRetentionSec=14day
JDEOF
systemctl restart systemd-journald 2>/dev/null || true
success "Log rotation configured (14 days retention)"

# ═══════════════════════════════════════════════════════════════════════════════
# Start the service & run health checks
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD} Starting PSK Bot & running health checks...${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

systemctl start ${SERVICE_NAME}

# Wait for the app to become healthy
info "Waiting for PSK Bot to start..."
HEALTHY=false
for i in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:${PORT}/api/v1/health" > /dev/null 2>&1; then
        HEALTHY=true
        break
    fi
    sleep 2
done

echo ""
echo -e "${BOLD}Service Status:${NC}"

# Check Ollama
if systemctl is-active --quiet ollama; then
    success "Ollama:    running"
else
    fail "Ollama:    NOT running"
fi

# Check PSK Bot
if systemctl is-active --quiet ${SERVICE_NAME}; then
    success "PSK Bot:   running"
else
    warn "PSK Bot:   not yet running (check: journalctl -u ${SERVICE_NAME} -n 50)"
fi

# Check Nginx
if systemctl is-active --quiet nginx; then
    success "Nginx:     running"
else
    warn "Nginx:     not running"
fi

# Health check
if [[ "$HEALTHY" == "true" ]]; then
    HEALTH_RESPONSE=$(curl -sf "http://127.0.0.1:${PORT}/api/v1/health" 2>/dev/null || echo '{}')
    success "Health:    OK"
    info "Response:  ${HEALTH_RESPONSE}"
else
    warn "Health check timed out — app may still be loading models"
    info "Check status: journalctl -u ${SERVICE_NAME} -f"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         Setup Complete!                                 ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BOLD}URLs:${NC}"
if [[ "$SKIP_SSL" == "true" ]]; then
    echo "  Web UI:          http://${DOMAIN}/"
    echo "  API Docs:        http://${DOMAIN}/docs/"
    echo "  Robot Chat:      POST http://${DOMAIN}/api/v1/chat"
    echo "  Robot Stream:    POST http://${DOMAIN}/api/v1/chat/stream"
    echo "  Health Check:    GET  http://${DOMAIN}/api/v1/health"
    echo "  Documents List:  GET  http://${DOMAIN}/api/v1/documents"
else
    echo "  Web UI:          https://${DOMAIN}/"
    echo "  API Docs:        https://${DOMAIN}/docs/"
    echo "  Robot Chat:      POST https://${DOMAIN}/api/v1/chat"
    echo "  Robot Stream:    POST https://${DOMAIN}/api/v1/chat/stream"
    echo "  Health Check:    GET  https://${DOMAIN}/api/v1/health"
    echo "  Documents List:  GET  https://${DOMAIN}/api/v1/documents"
fi
echo ""
echo -e "${BOLD}API Key:${NC}"
echo "  ${API_KEY}"
echo ""
echo -e "${BOLD}Quick Test:${NC}"
PROTO="https"
[[ "$SKIP_SSL" == "true" ]] && PROTO="http"
echo "  curl -X POST ${PROTO}://${DOMAIN}/api/v1/chat \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -H 'X-API-Key: ${API_KEY}' \\"
echo "    -d '{\"message\": \"Hello!\"}'"
echo ""
echo -e "${BOLD}Service Management:${NC}"
echo "  sudo systemctl status ${SERVICE_NAME}    # Check status"
echo "  sudo systemctl restart ${SERVICE_NAME}   # Restart app"
echo "  sudo systemctl stop ${SERVICE_NAME}      # Stop app"
echo "  sudo journalctl -u ${SERVICE_NAME} -f    # Live logs"
echo ""
echo -e "${BOLD}Upload Documents:${NC}"
echo "  Open https://${DOMAIN}/admin/ in your browser"
echo ""
if [[ "$SKIP_SSL" == "true" ]]; then
    echo -e "${YELLOW}SSL Setup (when DNS is ready):${NC}"
    echo "  sudo certbot --nginx -d ${DOMAIN}"
    echo ""
fi
echo -e "${BOLD}Files:${NC}"
echo "  App:      ${APP_DIR}/"
echo "  Config:   ${APP_DIR}/.env"
echo "  Service:  /etc/systemd/system/${SERVICE_NAME}.service"
echo "  Nginx:    /etc/nginx/sites-available/${SERVICE_NAME}"
echo "  Logs:     journalctl -u ${SERVICE_NAME}"
echo ""
