#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run as root" >&2
  exit 1
fi

repo_dir=${1:-/opt/google-workspace-mcp}
expected_rev=${EXPECTED_REV:-$(git -C "$repo_dir" rev-parse HEAD)}
unit="workspace-mcp-deploy-$(date -u +%Y%m%dT%H%M%SZ)"

systemd-run \
  --unit="$unit" \
  --collect \
  --property=Type=oneshot \
  --property=TimeoutStartSec=30min \
  --setenv="EXPECTED_REV=$expected_rev" \
  "$repo_dir/ops/deploy-hetzner.sh" "$repo_dir"

echo "Deployment started in $unit; it survives SSH disconnects."
echo "Follow it with: journalctl -fu $unit"
echo "Check completion with: systemctl show $unit -p Result -p ExecMainStatus"
