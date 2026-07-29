#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run as root" >&2
  exit 1
fi

repo_dir=${1:-/opt/google-workspace-mcp}
cd "$repo_dir"

# These indirections keep the host policy unchanged while making this script easy to
# exercise with command stubs in an isolated test directory.
docker_bin=${DOCKER_BIN:-docker}
git_bin=${GIT_BIN:-git}
df_bin=${DF_BIN:-df}
flock_bin=${FLOCK_BIN:-flock}
watchdog_bin=${WATCHDOG_INSTALL_BIN:-./ops/install-watchdog.sh}
lock_file=${DEPLOY_LOCK_FILE:-/run/lock/workspace-mcp-deploy.lock}
minimum_free_bytes=${MIN_ROOT_FREE_BYTES:-5368709120}

# A deploy must never overlap another deploy (including one started by systemd).
exec 9>"$lock_file"
if ! "$flock_bin" -n 9; then
  echo "Another deployment is already running ($lock_file)" >&2
  exit 1
fi

if [[ -n $($git_bin status --porcelain --untracked-files=no) ]]; then
  echo "Refusing to deploy a modified tracked worktree" >&2
  exit 1
fi

if [[ -n ${EXPECTED_REV:-} ]] && [[ $($git_bin rev-parse HEAD) != "$EXPECTED_REV" ]]; then
  echo "HEAD does not match EXPECTED_REV" >&2
  exit 1
fi

available_bytes=$($df_bin -P -B1 / | awk 'NR == 2 {print $4}')
if [[ ! $available_bytes =~ ^[0-9]+$ ]] || ((available_bytes < minimum_free_bytes)); then
  echo "Refusing to build with less than ${minimum_free_bytes} bytes free on the root filesystem" >&2
  exit 1
fi

"$docker_bin" compose config --quiet
stamp=${DEPLOY_STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}
declare -A old_images

declare -A image_refs
for service in workspace-personal-mcp workspace-business-mcp; do
  old_images[$service]=$($docker_bin inspect --format '{{.Image}}' "$service")
  image_refs[$service]=$($docker_bin inspect --format '{{.Config.Image}}' "$service")
  "$docker_bin" tag "${old_images[$service]}" "workspace-mcp-rollback:${stamp}-${service}"
done

active_service=
rollback_active() {
  local service=$active_service
  [[ -n $service ]] || return 0
  trap - ERR
  echo "Rolling back $service to ${old_images[$service]}" >&2
  "$docker_bin" tag "${old_images[$service]}" "${image_refs[$service]}"
  "$docker_bin" compose up -d --no-deps --no-build --force-recreate "$service"
}
trap rollback_active ERR

"$docker_bin" compose build

for service in workspace-personal-mcp workspace-business-mcp; do
  active_service=$service
  "$docker_bin" compose up -d --no-deps --no-build --force-recreate "$service"
  for _attempt in {1..18}; do
    if [[ $($docker_bin inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$service") == healthy ]]; then
      break
    fi
    sleep "${DEPLOY_SLEEP_SECONDS:-5}"
  done
  [[ $($docker_bin inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$service") == healthy ]]
  "$docker_bin" exec "$service" .venv/bin/workspace-cli \
    --url http://127.0.0.1:8000/mcp --no-auth --timeout 30 --json list
  if [[ $service == workspace-personal-mcp ]]; then
    smoke_tool=list_calendars
  else
    smoke_tool=list_gmail_labels
  fi
  "$docker_bin" exec "$service" .venv/bin/workspace-cli \
    --url http://127.0.0.1:8000/mcp --no-auth --timeout 30 call "$smoke_tool"
  active_service=
 done

# Both services have passed all probes. Only now discard generations older than
# the one captured for this rollout; never remove application images or volumes.
for service in workspace-personal-mcp workspace-business-mcp; do
  while IFS= read -r tag; do
    [[ -n $tag && $tag != "workspace-mcp-rollback:${stamp}-${service}" ]] || continue
    [[ $tag == workspace-mcp-rollback:*-${service} ]] || continue
    "$docker_bin" image rm "$tag"
  done < <("$docker_bin" image ls --format '{{.Repository}}:{{.Tag}}' 'workspace-mcp-rollback:*')
done
"$docker_bin" builder prune --force

trap - ERR
"$watchdog_bin" "$repo_dir"
echo "Workspace MCP rollout complete at $($git_bin rev-parse HEAD); rollback tag prefix: workspace-mcp-rollback:${stamp}"
