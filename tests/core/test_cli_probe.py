from types import SimpleNamespace

import pytest

from core import cli


class FakeClient:
    auth = "unset"

    def __init__(self, _url, auth=None):
        FakeClient.auth = auth

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def list_tools(self):
        return [
            SimpleNamespace(name="z_tool", description="Z"),
            SimpleNamespace(name="a_tool", description="A"),
        ]


@pytest.mark.asyncio
async def test_internal_json_probe_skips_oauth(monkeypatch, capsys):
    monkeypatch.setattr(cli, "Client", FakeClient)
    monkeypatch.setattr(
        cli, "_build_oauth", lambda: pytest.fail("OAuth should not be initialized")
    )

    await cli._list_tools("http://localhost/mcp", use_auth=False, json_output=True)

    assert FakeClient.auth is None
    payload = cli.json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["tool_count"] == 2
    assert payload["tool_names"] == ["a_tool", "z_tool"]


@pytest.mark.asyncio
async def test_probe_failure_is_machine_readable(monkeypatch, capsys):
    class BrokenClient(FakeClient):
        async def __aenter__(self):
            raise RuntimeError("secret detail must not be emitted")

    monkeypatch.setattr(cli, "Client", BrokenClient)

    with pytest.raises(SystemExit):
        await cli._list_tools("http://localhost/mcp", use_auth=False, json_output=True)

    payload = cli.json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error_type"] == "RuntimeError"
    assert "secret detail" not in str(payload)
