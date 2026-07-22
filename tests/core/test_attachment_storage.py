"""Tests for filename handling in core.attachment_storage."""

import time
import unicodedata
from urllib.parse import parse_qs, urlparse

import pytest

from core.attachment_storage import (
    _attachment_signature,
    get_attachment_url,
    sanitize_attachment_filename,
    validate_attachment_url_signature,
)

# Built via chr() so the source stays pure ASCII and the exact code points are
# unambiguous (these characters are visually indistinguishable from a space).
NARROW_NBSP = chr(0x202F)  # macOS screenshot time separator (NARROW NO-BREAK SPACE)


class TestSanitizeAttachmentFilename:
    """Unit tests for sanitize_attachment_filename."""

    def test_plain_filename_unchanged(self):
        assert sanitize_attachment_filename("report.pdf") == "report.pdf"

    def test_empty_returns_default(self):
        assert sanitize_attachment_filename("") == "attachment"

    def test_none_returns_default(self):
        assert sanitize_attachment_filename(None) == "attachment"

    def test_reserved_characters_replaced(self):
        assert sanitize_attachment_filename("a/b:c*d?.png") == "a_b_c_d_.png"

    def test_windows_reserved_name_prefixed(self):
        assert sanitize_attachment_filename("CON.txt") == "_CON.txt"

    def test_regular_ascii_space_preserved(self):
        assert sanitize_attachment_filename("my file.txt") == "my file.txt"

    def test_narrow_no_break_space_normalized_to_ascii_space(self):
        # macOS screenshots use U+202F (NARROW NO-BREAK SPACE) before "AM"/"PM".
        # Clients that echo the saved path back into a read/open call often
        # normalize U+202F to a regular space (U+0020); the saved name must use a
        # regular space too, or that read fails with "file not found".
        original = f"Screenshot 2026-05-28 at 3.44.08{NARROW_NBSP}PM.png"
        result = sanitize_attachment_filename(original)
        assert NARROW_NBSP not in result
        assert result == "Screenshot 2026-05-28 at 3.44.08 PM.png"

    def test_various_unicode_spaces_normalized(self):
        # NO-BREAK SPACE, THIN SPACE, NARROW NO-BREAK SPACE, IDEOGRAPHIC SPACE --
        # all Unicode "Zs" (space separator) code points.
        for cp in (0x00A0, 0x2009, 0x202F, 0x3000):
            sep = chr(cp)
            assert unicodedata.category(sep) == "Zs"
            assert sanitize_attachment_filename(f"a{sep}b.txt") == "a b.txt"


class TestExternalAttachmentUrls:
    file_id = "123e4567-e89b-12d3-a456-426614174000"
    signing_secret = "test-secret-at-least-thirty-two-bytes-long"

    def test_external_url_is_signed_and_short_lived(self, monkeypatch):
        monkeypatch.setenv("WORKSPACE_EXTERNAL_URL", "https://mcp.example.test/")
        monkeypatch.setenv("WORKSPACE_ATTACHMENT_SIGNING_SECRET", self.signing_secret)

        url = get_attachment_url(self.file_id)
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        assert parsed.scheme == "https"
        assert parsed.path == f"/attachments/{self.file_id}"
        assert set(query) == {"expires", "signature"}
        assert validate_attachment_url_signature(
            self.file_id, query["expires"][0], query["signature"][0]
        )
        assert int(query["expires"][0]) - int(time.time()) <= 300

    def test_external_url_without_secret_is_not_issued(self, monkeypatch):
        monkeypatch.setenv("WORKSPACE_EXTERNAL_URL", "https://mcp.example.test")
        monkeypatch.delenv("WORKSPACE_ATTACHMENT_SIGNING_SECRET", raising=False)

        with pytest.raises(RuntimeError, match="not configured"):
            get_attachment_url(self.file_id)

    def test_signature_rejects_expired_noncanonical_and_weak_secret(self, monkeypatch):
        monkeypatch.setenv("WORKSPACE_ATTACHMENT_SIGNING_SECRET", self.signing_secret)
        expires = int(time.time()) - 1
        signature = _attachment_signature(self.file_id, expires, self.signing_secret.encode())

        assert not validate_attachment_url_signature(self.file_id, str(expires), signature)
        assert not validate_attachment_url_signature("not-a-uuid", "9999999999", "x")
        monkeypatch.setenv("WORKSPACE_ATTACHMENT_SIGNING_SECRET", "too-short")
        assert not validate_attachment_url_signature(self.file_id, "9999999999", "x")
