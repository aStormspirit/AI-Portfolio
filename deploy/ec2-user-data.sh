#!/bin/bash
# EC2 user-data (cloud-init) for Amazon Linux 2023.
# Prepares Docker + Compose and installs a systemd service for the bot.
# Paste this as "User data" when launching the instance. It does NOT copy the
# app code or secrets — do that after boot (see deploy/README.md).
set -euxo pipefail

APP_DIR=/opt/portfolio-bot

dnf update -y
dnf install -y docker git
systemctl enable --now docker

# Docker Compose v2 plugin (not shipped by default on AL2023).
DOCKER_CLI_PLUGINS=/usr/local/lib/docker/cli-plugins
mkdir -p "$DOCKER_CLI_PLUGINS"
ARCH="$(uname -m)"
curl -fSL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-${ARCH}" \
  -o "$DOCKER_CLI_PLUGINS/docker-compose"
chmod +x "$DOCKER_CLI_PLUGINS/docker-compose"

usermod -aG docker ec2-user || true
mkdir -p "$APP_DIR"
chown -R ec2-user:ec2-user "$APP_DIR"

# systemd unit that runs docker compose in the foreground and restarts on failure.
cat >/etc/systemd/system/portfolio-bot.service <<'UNIT'
[Unit]
Description=Portfolio -> Reactive Resume Telegram bot
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/portfolio-bot
ExecStartPre=/usr/bin/docker compose build
ExecStart=/usr/bin/docker compose up
ExecStop=/usr/bin/docker compose down
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
# Enabled now; it will start once the code + .env are present in $APP_DIR.
systemctl enable portfolio-bot.service
