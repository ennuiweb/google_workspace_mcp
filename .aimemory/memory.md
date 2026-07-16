# google-workspace-mcp memory

- Purpose: canonical Ennui-owned source for the two fixed-account Google Workspace MCP services on `hetzner-ennui-vps-01`.
- Business: `admin@tjekdepot.dk`, loopback backend `127.0.0.1:8802`, Gmail/Drive/Docs/Sheets/Contacts.
- Personal: `oskar.vedel@gmail.com`, loopback backend `127.0.0.1:8803`, Gmail/Drive/Docs/Sheets/Slides/Calendar/Tasks/Contacts.
- Public access remains `nginx -> mcp-auth-proxy -> backend`; Google credentials remain in host-mounted per-account data directories.
- Dependency pins: MCP SDK `11869e0ab5977d5ced8f13747af6e396599d0b5b`; FastMCP `1ac9717e3aa6c990e69c61751f10e590e2b97a8f`.
- Reliability: early-response stream cleanup prevents pre-session leaks; stateful sessions expire after 900 idle seconds; a five-minute protocol watchdog validates `initialize`/`tools/list` and performs bounded per-container recovery after two failures (one restart/hour, three/day).
- Deployment and rollback commands live under `ops/`; runtime secrets and health state remain outside Git.
