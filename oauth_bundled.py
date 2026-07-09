"""Bundled OAuth — end users sign in only; developer configures once at build time."""

import json
from pathlib import Path

from config import APP_DIR, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_CREDENTIALS_FILE


def read_google_credentials_file(path: Path) -> tuple[str, str]:
    if not path.exists():
        return "", ""
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    section = data.get("web") or data.get("installed") or {}
    return section.get("client_id", ""), section.get("client_secret", "")


def bundled_google_credentials() -> tuple[str, str]:
    """Credentials shipped with the app (installer or credentials.json)."""
    if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
        return GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
    return read_google_credentials_file(GOOGLE_CREDENTIALS_FILE)


def is_google_oauth_bundled() -> bool:
    client_id, client_secret = bundled_google_credentials()
    return bool(client_id and client_secret)


def seed_google_oauth_settings(store) -> bool:
    """Copy bundled credentials into the local DB so sign-in works out of the box."""
    if store.get_setting("oauth_google_client_id") and store.get_setting("oauth_google_client_secret"):
        return False
    client_id, client_secret = bundled_google_credentials()
    if not client_id or not client_secret:
        return False
    store.set_setting("oauth_google_client_id", client_id)
    store.set_setting("oauth_google_client_secret", client_secret)
    store.set_setting("active_cloud_provider", "google_drive")
    return True
