#!/usr/bin/env python3
"""Protocol-level health check and bounded recovery for Workspace MCP containers."""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOG = logging.getLogger("workspace-mcp-watchdog")
STATE_VERSION = 1
FAILURES_BEFORE_RESTART = 2
RESTART_COOLDOWN_SECONDS = 3600
RESTART_WINDOW_SECONDS = 86400
MAX_RESTARTS_PER_WINDOW = 3


@dataclass(frozen=True)
class Target:
    name: str
    minimum_tools: int
    required_tools: frozenset[str]


TARGETS = (
    Target(
        "workspace-business-mcp",
        20,
        frozenset({"search_gmail_messages", "search_drive_files", "get_doc_content"}),
    ),
    Target(
        "workspace-personal-mcp",
        30,
        frozenset(
            {
                "search_gmail_messages",
                "search_drive_files",
                "get_doc_content",
                "list_calendars",
            }
        ),
    ),
)


def run_command(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def protocol_probe(target: Target) -> tuple[bool, str]:
    command = [
        "docker",
        "exec",
        target.name,
        ".venv/bin/workspace-cli",
        "--url",
        "http://127.0.0.1:8000/mcp",
        "--no-auth",
        "--timeout",
        "30",
        "--json",
        "list",
    ]
    try:
        result = run_command(command, timeout=40)
    except subprocess.TimeoutExpired:
        return False, "protocol probe exceeded 40 seconds"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-500:]
        return False, f"protocol probe exited {result.returncode}: {detail}"
    try:
        payload = json.loads(result.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return False, "protocol probe returned invalid JSON"
    if payload.get("ok") is not True:
        return False, f"protocol probe reported failure: {payload}"
    names = set(payload.get("tool_names", []))
    missing = sorted(target.required_tools - names)
    count = payload.get("tool_count")
    if not isinstance(count, int) or count < target.minimum_tools:
        return False, f"tool count {count!r} is below {target.minimum_tools}"
    if missing:
        return False, f"required tools missing: {', '.join(missing)}"
    return True, f"{count} tools in {payload.get('duration_seconds', '?')}s"


def load_state(path: Path) -> dict[str, Any]:
    try:
        state = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"version": STATE_VERSION, "targets": {}}
    if state.get("version") != STATE_VERSION or not isinstance(
        state.get("targets"), dict
    ):
        return {"version": STATE_VERSION, "targets": {}}
    return state


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def capture_diagnostics(target: Target) -> None:
    for command in (
        [
            "docker",
            "inspect",
            "--format",
            "{{json .State}}",
            target.name,
        ],
        ["docker", "logs", "--tail", "150", target.name],
    ):
        try:
            result = run_command(command, timeout=20)
        except subprocess.TimeoutExpired:
            LOG.error("diagnostic command timed out: %s", " ".join(command))
            continue
        output = (result.stdout + result.stderr).strip()
        LOG.error(
            "diagnostics for %s (%s):\n%s",
            target.name,
            " ".join(command),
            output[-12000:],
        )


def restart_allowed(target_state: dict[str, Any], now: float) -> tuple[bool, str]:
    restarts = [
        float(value)
        for value in target_state.get("restart_timestamps", [])
        if now - float(value) < RESTART_WINDOW_SECONDS
    ]
    target_state["restart_timestamps"] = restarts
    if restarts and now - restarts[-1] < RESTART_COOLDOWN_SECONDS:
        return False, "restart cooldown active"
    if len(restarts) >= MAX_RESTARTS_PER_WINDOW:
        return False, "daily restart limit reached"
    return True, "allowed"


def check_target(target: Target, state: dict[str, Any], now: float) -> bool:
    target_state = state["targets"].setdefault(
        target.name, {"consecutive_failures": 0, "restart_timestamps": []}
    )
    ok, detail = protocol_probe(target)
    target_state["last_check"] = now
    target_state["last_detail"] = detail
    if ok:
        target_state["consecutive_failures"] = 0
        target_state["last_success"] = now
        LOG.info("%s healthy: %s", target.name, detail)
        return True

    failures = int(target_state.get("consecutive_failures", 0)) + 1
    target_state["consecutive_failures"] = failures
    LOG.error(
        "%s failed protocol probe (%s/%s): %s",
        target.name,
        failures,
        FAILURES_BEFORE_RESTART,
        detail,
    )
    if failures < FAILURES_BEFORE_RESTART:
        return False

    allowed, reason = restart_allowed(target_state, now)
    if not allowed:
        LOG.critical(
            "%s remains unhealthy; automatic recovery suppressed: %s",
            target.name,
            reason,
        )
        return False

    capture_diagnostics(target)
    result = run_command(["docker", "restart", "--time", "30", target.name], timeout=60)
    if result.returncode != 0:
        LOG.critical(
            "failed to restart %s: %s",
            target.name,
            (result.stderr or result.stdout).strip(),
        )
        return False
    target_state.setdefault("restart_timestamps", []).append(now)
    target_state["last_restart"] = now
    time.sleep(15)
    recovered, recovery_detail = protocol_probe(target)
    target_state["last_detail"] = recovery_detail
    if recovered:
        target_state["consecutive_failures"] = 0
        target_state["last_success"] = time.time()
        LOG.warning(
            "%s recovered after bounded restart: %s", target.name, recovery_detail
        )
        return True
    LOG.critical(
        "%s restart did not restore protocol health: %s", target.name, recovery_detail
    )
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path("/var/lib/workspace-mcp-watchdog/state.json"),
    )
    parser.add_argument(
        "--target", choices=[target.name for target in TARGETS], action="append"
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    state = load_state(args.state_file)
    selected = [
        target for target in TARGETS if not args.target or target.name in args.target
    ]
    now = time.time()
    results = [check_target(target, state, now) for target in selected]
    healthy = all(results)
    save_state(args.state_file, state)
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
