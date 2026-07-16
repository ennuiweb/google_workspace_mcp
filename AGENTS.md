## Repo Identity

- Name: `google-workspace-mcp`
- Type: `repo`
- Absolute path: `/Users/oskar/repo/google-workspace-mcp`
- Role: Ennui-owned Google Workspace MCP fork and canonical two-account Hetzner deployment source
- Global reference: `/Users/oskar/.agents/AGENTS.md`

## Inheritance From Global AGENTS

- Global rules in `/Users/oskar/.agents/AGENTS.md` apply by default.
- This file adds only fork and deployment-specific rules.

## Repo-local Rules

- Keep `upstream` pointed at `taylorwilsdon/google_workspace_mcp` and `origin` pointed at `ennuiweb/google_workspace_mcp`.
- The business and personal services are fixed-account deployments; do not broaden account routing.
- Never commit `.env.*`, Google OAuth client secrets, credential stores, attachments, or runtime health state.
- Production changes require tests, image rebuild, staged container rollout, protocol-level MCP probes, Google read smokes, and public OAuth-edge validation.
- Pin the MCP SDK maintenance revision exactly; do not float a Git dependency used in production.

## Local Context Map

- `docker-compose.yml` — canonical two-account Hetzner service definition
- `core/server.py` — FastMCP construction and HTTP middleware
- `core/cli.py` — authenticated and internal protocol probes
- `ops/` — health watchdog, systemd assets, deploy and rollback tooling
- `ops/README.md` — production reliability, deployment, validation, and rollback procedure
- `tests/` — unit and protocol regression tests
- `.aimemory/memory.md` — production snapshot, dependency pin, and operating notes

## Self-maintenance Rules

- Update `.aimemory/memory.md` when the production revision, dependency pin, watchdog behavior, or deployment topology changes.
- Update the Hetzner operations repo when URLs, ports, services, deploy paths, or recovery commands change.
- If repo identity or role changes, update the global registry and this file together.
