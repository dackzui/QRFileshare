from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ProviderId = Literal["google_drive", "dropbox", "onedrive", "cloud_link"]
AuthType = Literal["oauth", "none"]


@dataclass(frozen=True)
class ProviderInfo:
    id: ProviderId
    name: str
    description: str
    auth_type: AuthType
    supports_upload: bool
    supports_sync: bool
    setup_hint: str
    dev_console_url: str


PROVIDERS: dict[str, ProviderInfo] = {
    "google_drive": ProviderInfo(
        id="google_drive",
        name="Google Drive",
        description="Create folders, upload files, and share with Google sign-in.",
        auth_type="oauth",
        supports_upload=True,
        supports_sync=True,
        setup_hint="Click Sign in — uses app OAuth settings from Cloud Storage below.",
        dev_console_url="https://console.cloud.google.com/apis/credentials",
    ),
    "dropbox": ProviderInfo(
        id="dropbox",
        name="Dropbox",
        description="Sync folders and files with your Dropbox account.",
        auth_type="oauth",
        supports_upload=True,
        supports_sync=True,
        setup_hint="Sign in with Dropbox after saving app credentials once (Settings).",
        dev_console_url="https://www.dropbox.com/developers/apps",
    ),
    "onedrive": ProviderInfo(
        id="onedrive",
        name="OneDrive",
        description="Microsoft OneDrive and SharePoint personal storage.",
        auth_type="oauth",
        supports_upload=True,
        supports_sync=True,
        setup_hint="Sign in with Microsoft after saving Azure app credentials once.",
        dev_console_url="https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps",
    ),
    "cloud_link": ProviderInfo(
        id="cloud_link",
        name="Other cloud link",
        description="Paste any existing folder link (Drive, Dropbox, Box, etc.) for QR sharing only.",
        auth_type="none",
        supports_upload=False,
        supports_sync=False,
        setup_hint="No sign-in needed — paste your folder URL when creating a folder.",
        dev_console_url="",
    ),
}


def get_provider_info(provider_id: str) -> ProviderInfo | None:
    return PROVIDERS.get(provider_id)
