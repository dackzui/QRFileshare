"""Open the user's email app with a pre-filled share message."""

from __future__ import annotations

import re
from urllib.parse import quote

from version_info import get_app_info
from database import ShareLink
from share_service import format_expiry

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailComposeError(Exception):
    pass


def is_valid_email(address: str) -> bool:
    return bool(EMAIL_RE.match((address or "").strip()))


def build_share_email_body(
    *,
    link: ShareLink,
    share_url: str,
    sender_label: str | None = None,
) -> tuple[str, str]:
    info = get_app_info()
    sender_label = sender_label or str(info["app_author"])
    app_name = str(info["app_name"])
    title = link.label or "Shared folder"
    subject = f"{title} — shared via {app_name}"
    expiry_line = format_expiry(link)
    time_left = link.time_remaining
    body = f"""Hello,

{sender_label} has shared a folder with you via {app_name}.

Folder: {title}

Google Drive link:
{link.target_url}

Link validity:
This folder share is valid until {expiry_line} ({time_left}).
After that date, the expiring share link will stop working. The QR code links directly to Google Drive.

Please attach the QR code image before sending.

—
{app_name}
"""
    return subject, body


def build_mailto_url(to_email: str, subject: str, body: str) -> str:
    return (
        f"mailto:{quote(to_email)}"
        f"?subject={quote(subject)}"
        f"&body={quote(body)}"
    )


def build_gmail_compose_url(to_email: str, subject: str, body: str) -> str:
    return (
        "https://mail.google.com/mail/?view=cm&fs=1"
        f"&to={quote(to_email)}"
        f"&su={quote(subject)}"
        f"&body={quote(body)}"
    )


def compose_share_email(
    *,
    to_email: str,
    link: ShareLink,
    share_url: str,
    sender_label: str | None = None,
) -> tuple[str, str, str]:
    to_email = to_email.strip()
    if not is_valid_email(to_email):
        raise EmailComposeError("Enter a valid email address.")

    subject, body = build_share_email_body(
        link=link,
        share_url=share_url,
        sender_label=sender_label,
    )
    mailto_url = build_mailto_url(to_email, subject, body)
    gmail_url = build_gmail_compose_url(to_email, subject, body)
    return mailto_url, gmail_url, subject
