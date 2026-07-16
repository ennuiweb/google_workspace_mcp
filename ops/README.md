# Oskar deployment operations

This fork is the canonical source for the two fixed-account services on `hetzner-ennui-vps-01`. Production runs from `/opt/google-workspace-mcp` and exposes only loopback ports `8802` (business) and `8803` (personal); nginx and `mcp-auth-proxy` own the public OAuth edge.

## Reliability model

The incident fixed in July 2026 had two contributing lifecycle gaps: requests rejected before a fully initialized MCP session could leave response streams open, and stateful sessions had no idle expiry. The pinned Ennui MCP SDK closes request-owned streams on every early response. The pinned FastMCP fork exposes the SDK idle timeout, configured to 900 seconds in Compose.

`workspace-mcp-watchdog.timer` runs every five minutes. Its probe performs a real MCP initialize and `tools/list` from inside each container, validates a minimum tool count and sentinel tools, and closes the client normally. Two consecutive failures trigger diagnostics and a restart of only the affected container. Recovery is limited to one restart per hour and three per rolling day. Persistent failures and suppressed restarts are emitted at critical priority in the service journal.

The shallow `/health` endpoint remains a Docker readiness check. It is intentionally not treated as proof that MCP handshaking works.

## Deploy

Before production rollout, run the unit suite and build the image. Preserve the current revision and image ID for rollback. Roll out personal first, verify its protocol probe and a read-only Google tool, then repeat for business. Start the host rollout through the transient systemd wrapper so an SSH disconnect cannot leave a recreated container stopped.

```bash
uv sync --locked --extra dev
uv run pytest -m "not integration"
docker compose config --quiet
docker compose build

sudo EXPECTED_REV=$(git rev-parse HEAD) ./ops/start-deploy-hetzner.sh /opt/google-workspace-mcp
sudo ./ops/install-watchdog.sh /opt/google-workspace-mcp
sudo /usr/local/sbin/workspace-mcp-watchdog
```

Useful production checks:

```bash
docker compose ps
docker exec workspace-business-mcp .venv/bin/workspace-cli --url http://127.0.0.1:8000/mcp --no-auth --timeout 30 --json list
docker exec workspace-personal-mcp .venv/bin/workspace-cli --url http://127.0.0.1:8000/mcp --no-auth --timeout 30 --json list
docker exec workspace-business-mcp .venv/bin/workspace-cli --url http://127.0.0.1:8000/mcp --no-auth --timeout 30 call list_gmail_labels
docker exec workspace-personal-mcp .venv/bin/workspace-cli --url http://127.0.0.1:8000/mcp --no-auth --timeout 30 call list_calendars
systemctl status workspace-mcp-watchdog.timer
journalctl -u workspace-mcp-watchdog.service --since today
```

The deploy wrapper prints a transient unit name. Follow that unit with `journalctl -fu <unit>` and require `Result=success` plus `ExecMainStatus=0` before treating the rollout as complete.

## Rollback

Checkout the recorded pre-deploy revision, restore its Compose file if necessary, rebuild, and recreate only the affected service. Do not delete or replace `business/data`, `personal/data`, `.env.business`, `.env.personal`, or `client_secret.json`; those are host-owned state and secrets.

The watchdog state is diagnostic only. A corrupt state file fails safe to an empty state, and deleting it is not required for application rollback.
