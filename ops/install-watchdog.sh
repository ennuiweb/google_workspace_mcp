#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run as root" >&2
  exit 1
fi

repo_dir=${1:-/opt/google-workspace-mcp}
install -m 0755 "$repo_dir/ops/workspace_mcp_watchdog.py" /usr/local/sbin/workspace-mcp-watchdog
install -m 0644 "$repo_dir/ops/systemd/workspace-mcp-watchdog.service" /etc/systemd/system/workspace-mcp-watchdog.service
install -m 0644 "$repo_dir/ops/systemd/workspace-mcp-watchdog.timer" /etc/systemd/system/workspace-mcp-watchdog.timer
systemctl daemon-reload
systemctl enable --now workspace-mcp-watchdog.timer
systemctl start workspace-mcp-watchdog.service
