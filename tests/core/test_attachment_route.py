import time

import pytest
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse

from core.attachment_storage import _attachment_signature
from core.server import serve_attachment


FILE_ID = "123e4567-e89b-12d3-a456-426614174000"


def _build_request(file_id: str, query_string: bytes = b"") -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": f"/attachments/{file_id}",
        "raw_path": f"/attachments/{file_id}".encode(),
        "query_string": query_string,
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("localhost", 8000),
        "path_params": {"file_id": file_id},
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


@pytest.mark.asyncio
async def test_serve_attachment_uses_path_param_file_id(monkeypatch, tmp_path):
    file_path = tmp_path / "sample.pdf"
    file_path.write_bytes(b"%PDF-1.3\n")
    captured = {}

    class DummyStorage:
        def get_attachment_metadata(self, file_id):
            captured["file_id"] = file_id
            return {"filename": "sample.pdf", "mime_type": "application/pdf"}

        def get_attachment_path(self, _file_id):
            return file_path

    monkeypatch.setattr(
        "core.attachment_storage.get_attachment_storage", lambda: DummyStorage()
    )

    response = await serve_attachment(_build_request(FILE_ID))

    assert captured["file_id"] == FILE_ID
    assert isinstance(response, FileResponse)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.asyncio
async def test_serve_attachment_404_when_metadata_missing(monkeypatch):
    class DummyStorage:
        def get_attachment_metadata(self, _file_id):
            return None

    monkeypatch.setattr(
        "core.attachment_storage.get_attachment_storage", lambda: DummyStorage()
    )

    response = await serve_attachment(_build_request(FILE_ID))

    assert isinstance(response, JSONResponse)
    assert response.status_code == 404
    assert b"Attachment not found or expired" in response.body
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.asyncio
async def test_serve_attachment_rejects_invalid_id_before_storage_lookup(monkeypatch):
    class DummyStorage:
        def get_attachment_metadata(self, _file_id):
            raise AssertionError("storage must not be queried for invalid IDs")

    monkeypatch.setattr(
        "core.attachment_storage.get_attachment_storage", lambda: DummyStorage()
    )

    response = await serve_attachment(_build_request("not-a-uuid"))

    assert response.status_code == 404
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.asyncio
async def test_serve_attachment_requires_valid_signature_for_external_url(monkeypatch):
    monkeypatch.setenv("WORKSPACE_EXTERNAL_URL", "https://mcp.example.test")
    monkeypatch.setenv("WORKSPACE_ATTACHMENT_SIGNING_SECRET", "test-secret")

    class DummyStorage:
        def get_attachment_metadata(self, _file_id):
            raise AssertionError("storage must not be queried without a valid signature")

    monkeypatch.setattr(
        "core.attachment_storage.get_attachment_storage", lambda: DummyStorage()
    )

    response = await serve_attachment(_build_request(FILE_ID))

    assert response.status_code == 403
    assert response.headers["cache-control"] == "private, no-store"

    class ValidTokenStorage:
        def get_attachment_metadata(self, _file_id):
            return None

    monkeypatch.setattr(
        "core.attachment_storage.get_attachment_storage", lambda: ValidTokenStorage()
    )
    expires = int(time.time()) + 60
    signature = _attachment_signature(FILE_ID, expires, b"test-secret")
    query = f"expires={expires}&signature={signature}".encode()
    response = await serve_attachment(_build_request(FILE_ID, query))
    assert response.status_code == 404
