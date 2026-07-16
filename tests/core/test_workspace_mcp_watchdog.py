import json
from types import SimpleNamespace

from ops import workspace_mcp_watchdog as watchdog


def test_protocol_probe_validates_count_and_sentinels(monkeypatch):
    target = watchdog.Target("test", 2, frozenset({"one", "two"}))
    payload = {
        "ok": True,
        "tool_count": 2,
        "tool_names": ["one", "two"],
        "duration_seconds": 0.1,
    }
    monkeypatch.setattr(
        watchdog,
        "run_command",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0, stdout=json.dumps(payload), stderr=""
        ),
    )

    assert watchdog.protocol_probe(target)[0] is True


def test_restart_is_bounded_by_cooldown_and_daily_limit():
    now = 100_000.0
    state = {"restart_timestamps": [now - 100]}
    assert watchdog.restart_allowed(state, now) == (False, "restart cooldown active")

    state = {"restart_timestamps": [now - 80000, now - 70000, now - 50000]}
    assert watchdog.restart_allowed(state, now) == (
        False,
        "daily restart limit reached",
    )


def test_corrupt_state_fails_safe(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("not-json")
    assert watchdog.load_state(path) == {"version": 1, "targets": {}}
