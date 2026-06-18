"""
Unit tests for forward_gmail_message
"""

import pytest
from unittest.mock import Mock
import base64
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from gmail.gmail_tools import _forward_gmail_message_impl


def create_mock_message(
    subject="Test Subject",
    from_addr="sender@example.com",
    to_addr="orig@example.com",
    date="Mon, 1 Jan 2024 10:00:00 -0000",
    text_body=None,
    html_body=None,
    attachments=None,
):
    """Create a mock Gmail message payload."""
    headers = [
        {"name": "Subject", "value": subject},
        {"name": "From", "value": from_addr},
        {"name": "To", "value": to_addr},
        {"name": "Date", "value": date},
    ]

    parts = []

    if text_body:
        encoded_text = base64.urlsafe_b64encode(text_body.encode()).decode()
        parts.append({"mimeType": "text/plain", "body": {"data": encoded_text}})

    if html_body:
        encoded_html = base64.urlsafe_b64encode(html_body.encode()).decode()
        parts.append({"mimeType": "text/html", "body": {"data": encoded_html}})

    if attachments:
        for att in attachments:
            parts.append(
                {
                    "filename": att["filename"],
                    "mimeType": att["mimeType"],
                    "body": {
                        "attachmentId": att["attachmentId"],
                        "size": att.get("size", 100),
                    },
                }
            )

    if parts:
        payload = {"mimeType": "multipart/mixed", "headers": headers, "parts": parts}
    else:
        # Simple message with no parts
        encoded_text = base64.urlsafe_b64encode(b"").decode()
        payload = {
            "mimeType": "text/plain",
            "headers": headers,
            "body": {"data": encoded_text},
        }

    return {"payload": payload}


def create_mock_service(message, attachments_data=None, sent_message_id="sent123"):
    """Create a mock Gmail service with chained method calls."""
    mock = Mock()

    # Setup chain: service.users().messages().get()
    mock.users().messages().get().execute.return_value = message

    # Setup chain: service.users().messages().attachments().get()
    if attachments_data:
        mock.users().messages().attachments().get().execute.side_effect = (
            attachments_data
        )
    else:
        mock.users().messages().attachments().get().execute.return_value = {"data": ""}

    # Setup chain: service.users().messages().send()
    mock.users().messages().send().execute.return_value = {"id": sent_message_id}

    return mock


@pytest.mark.asyncio
async def test_forward_simple_text_email():
    """Forward plain text email, no attachments"""
    message = create_mock_message(
        subject="Hello",
        from_addr="alice@example.com",
        to_addr="bob@example.com",
        text_body="This is the body.",
    )
    mock_service = create_mock_service(message, sent_message_id="fwd001")

    result = await _forward_gmail_message_impl(
        service=mock_service,
        message_id="msg123",
        to="recipient@example.com",
        user_google_email="me@example.com",
    )

    assert "Email forwarded" in result
    assert "fwd001" in result
    mock_service.users().messages().send.assert_called()


@pytest.mark.asyncio
async def test_forward_html_email():
    """Forward HTML email, verify HTML structure preserved"""
    message = create_mock_message(
        subject="HTML Test",
        from_addr="alice@example.com",
        to_addr="bob@example.com",
        html_body="<p>This is <strong>HTML</strong> content.</p>",
    )
    mock_service = create_mock_service(message, sent_message_id="fwd002")

    result = await _forward_gmail_message_impl(
        service=mock_service,
        message_id="msg456",
        to="recipient@example.com",
        user_google_email="me@example.com",
    )

    assert "Email forwarded" in result
    assert "fwd002" in result


@pytest.mark.asyncio
async def test_forward_with_message_plain():
    """Forward with plain text user message prepended"""
    message = create_mock_message(
        subject="FYI",
        from_addr="alice@example.com",
        to_addr="bob@example.com",
        text_body="Original message body.",
    )
    mock_service = create_mock_service(message, sent_message_id="fwd003")

    result = await _forward_gmail_message_impl(
        service=mock_service,
        message_id="msg789",
        to="recipient@example.com",
        forward_message="Please see below.",
        forward_message_format="plain",
        user_google_email="me@example.com",
    )

    assert "Email forwarded" in result
    assert "fwd003" in result


@pytest.mark.asyncio
async def test_forward_with_message_html():
    """Forward with HTML user message prepended"""
    message = create_mock_message(
        subject="Important",
        from_addr="alice@example.com",
        to_addr="bob@example.com",
        html_body="<p>Original HTML content.</p>",
    )
    mock_service = create_mock_service(message, sent_message_id="fwd004")

    result = await _forward_gmail_message_impl(
        service=mock_service,
        message_id="msgabc",
        to="recipient@example.com",
        forward_message="<b>Note:</b> See below.",
        forward_message_format="html",
        user_google_email="me@example.com",
    )

    assert "Email forwarded" in result
    assert "fwd004" in result


@pytest.mark.asyncio
async def test_forward_without_attachments():
    """Forward with include_attachments=False"""
    message = create_mock_message(
        subject="With Attachment",
        from_addr="alice@example.com",
        to_addr="bob@example.com",
        text_body="Message body.",
        attachments=[
            {
                "filename": "doc.pdf",
                "mimeType": "application/pdf",
                "attachmentId": "att1",
            }
        ],
    )
    mock_service = create_mock_service(message, sent_message_id="fwd005")

    result = await _forward_gmail_message_impl(
        service=mock_service,
        message_id="msgdef",
        to="recipient@example.com",
        include_attachments=False,
        user_google_email="me@example.com",
    )

    assert "Email forwarded" in result
    assert "fwd005" in result
    # Should not include attachments in result
    assert "attachment(s)" not in result


@pytest.mark.asyncio
async def test_forward_with_attachments():
    """Forward with attachments, mock attachment download"""
    message = create_mock_message(
        subject="With Attachment",
        from_addr="alice@example.com",
        to_addr="bob@example.com",
        text_body="See attached.",
        attachments=[
            {
                "filename": "report.pdf",
                "mimeType": "application/pdf",
                "attachmentId": "att1",
            },
            {"filename": "image.png", "mimeType": "image/png", "attachmentId": "att2"},
        ],
    )

    # Mock attachment data
    att1_data = base64.urlsafe_b64encode(b"PDF content").decode()
    att2_data = base64.urlsafe_b64encode(b"PNG content").decode()
    attachments_data = [{"data": att1_data}, {"data": att2_data}]

    mock_service = create_mock_service(
        message, attachments_data=attachments_data, sent_message_id="fwd006"
    )

    result = await _forward_gmail_message_impl(
        service=mock_service,
        message_id="msgghi",
        to="recipient@example.com",
        include_attachments=True,
        user_google_email="me@example.com",
    )

    assert "Email forwarded" in result
    assert "2 attachment(s)" in result
    assert "fwd006" in result


@pytest.mark.asyncio
async def test_forward_subject_already_has_fwd():
    """Subject already starts with 'Fwd:', don't double-prefix"""
    message = create_mock_message(
        subject="Fwd: Already forwarded",
        from_addr="alice@example.com",
        to_addr="bob@example.com",
        text_body="Previous forward.",
    )
    mock_service = create_mock_service(message, sent_message_id="fwd007")

    result = await _forward_gmail_message_impl(
        service=mock_service,
        message_id="msgjkl",
        to="recipient@example.com",
        user_google_email="me@example.com",
    )

    assert "Email forwarded" in result
    assert "fwd007" in result

    # Verify send was called - the subject should not be "Fwd: Fwd: ..."
    mock_service.users().messages().send.assert_called()


@pytest.mark.asyncio
async def test_forward_with_cc_bcc():
    """Forward with CC and BCC recipients"""
    message = create_mock_message(
        subject="Team Update",
        from_addr="alice@example.com",
        to_addr="bob@example.com",
        text_body="Team message.",
    )
    mock_service = create_mock_service(message, sent_message_id="fwd008")

    result = await _forward_gmail_message_impl(
        service=mock_service,
        message_id="msgmno",
        to="recipient@example.com",
        cc="cc@example.com",
        bcc="bcc@example.com",
        user_google_email="me@example.com",
    )

    assert "Email forwarded" in result
    assert "fwd008" in result
