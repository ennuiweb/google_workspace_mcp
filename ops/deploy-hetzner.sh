#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run as root" >&2
  exit 1
fi

repo_dir=${1:-/opt/google-workspace-mcp}
cd "$repo_dir"

if [[ -n $(git status --porcelain --untracked-files=no) ]]; then
  echo "Refusing to deploy a modified tracked worktree" >&2
  exit 1
fi

if [[ -n ${EXPECTED_REV:-} ]] && [[ $(git rev-parse HEAD) != "$EXPECTED_REV" ]]; then
  echo "HEAD does not match EXPECTED_REV" >&2
  exit 1
fi

docker compose config --quiet
stamp=$(date -u +%Y%m%dT%H%M%SZ)
declare -A old_images
declare -A image_refs
for service in workspace-personal-mcp workspace-business-mcp; do
  old_images[$service]=$(docker inspect --format '{{.Image}}' "$service")
  image_refs[$service]=$(docker inspect --format '{{.Config.Image}}' "$service")
  docker tag "${old_images[$service]}" "workspace-mcp-rollback:${stamp}-${service}"
done

active_service=
rollback_active() {
  local service=$active_service
  [[ -n $service ]] || return 0
  echo "Rolling back $service to ${old_images[$service]}" >&2
  docker tag "${old_images[$service]}" "${image_refs[$service]}"
  docker compose up -d --no-deps --no-build --force-recreate "$service"
}
trap rollback_active ERR

docker compose build

for service in workspace-personal-mcp workspace-business-mcp; do
  active_service=$service
  docker compose up -d --no-deps --no-build --force-recreate "$service"
  for _attempt in {1..18}; do
    if [[ $(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$service") == healthy ]]; then
      break
    fi
    sleep 5
  done
  [[ $(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$service") == healthy ]]
  docker exec "$service" .venv/bin/workspace-cli \
    --url http://127.0.0.1:8000/mcp --no-auth --timeout 30 --json list
  if [[ $service == workspace-personal-mcp ]]; then
    smoke_tool=list_calendars
  else
    smoke_tool=list_gmail_labels
  fi
  docker exec "$service" .venv/bin/workspace-cli \
    --url http://127.0.0.1:8000/mcp --no-auth --timeout 30 call "$smoke_tool"
  active_service=
done

./ops/install-watchdog.sh "$repo_dir"
trap - ERR
echo "Workspace MCP rollout complete at $(git rev-parse HEAD); rollback tag prefix: workspace-mcp-rollback:${stamp}"
