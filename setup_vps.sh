#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="marketpulse"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "=================================================="
echo "         MarketPulse VPS Deployer"
echo "=================================================="
echo "Project Path: $PROJECT_DIR"
echo ""

# 1. Setup Virtual Environment
if [ ! -d "$PROJECT_DIR/.venv" ]; then
    echo "[*] Creating virtual environment (.venv)..."
    python3 -m venv "$PROJECT_DIR/.venv"
else
    echo "[✅] Virtual environment (.venv) already exists."
fi

# 2. Install Dependencies
echo "[*] Installing/updating requirements..."
source "$PROJECT_DIR/.venv/bin/activate"
pip install --upgrade pip
pip install httpx yfinance beautifulsoup4 feedparser pytz python-dotenv

# 3. Create systemd Service File (requires sudo)
echo "[*] Creating systemd service file..."
sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=MarketPulse Corporate Catalyst & Macro Briefing Daemon
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/.venv/bin/python monitor.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

echo "[✅] Service file created: $SERVICE_FILE"

# 4. Reload and Start Service
echo "[*] Reloading systemd daemon..."
sudo systemctl daemon-reload

echo "[*] Enabling $SERVICE_NAME service (will launch on VM boot)..."
sudo systemctl enable "$SERVICE_NAME".service

echo "[*] Starting $SERVICE_NAME service..."
sudo systemctl restart "$SERVICE_NAME".service

echo ""
echo "=================================================="
echo "🎉 DEPLOYMENT COMPLETE! MarketPulse is running."
echo "=================================================="
echo "• Check status:  sudo systemctl status $SERVICE_NAME"
echo "• Stream logs:   journalctl -u $SERVICE_NAME -f"
echo "=================================================="
echo ""
