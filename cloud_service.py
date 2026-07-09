from __future__ import annotations

from cloud_providers.base import CloudProviderError, CreatedFolder, RemoteFile
from cloud_providers.dropbox_provider import DropboxProvider
from cloud_providers.google_drive import GoogleDriveProvider
from cloud_providers.link_provider import CloudLinkProvider
from cloud_providers.onedrive_provider import OneDriveProvider
from cloud_providers.registry import PROVIDERS, ProviderInfo, get_provider_info
from database import DataStore


class CloudService:
    def __init__(self, store: DataStore | None = None) -> None:
        self.store = store or DataStore()
        self._providers = {
            "google_drive": GoogleDriveProvider(self.store),
            "dropbox": DropboxProvider(self.store),
            "onedrive": OneDriveProvider(self.store),
            "cloud_link": CloudLinkProvider(),
        }

    def list_providers(self) -> list[ProviderInfo]:
        return list(PROVIDERS.values())

    def get_active_provider_id(self) -> str:
        value = self.store.get_setting("active_cloud_provider", "google_drive")
        return value if value in PROVIDERS else "google_drive"

    def set_active_provider(self, provider_id: str) -> None:
        if provider_id not in PROVIDERS:
            raise CloudProviderError("Unknown cloud provider.")
        self.store.set_setting("active_cloud_provider", provider_id)

    def provider(self, provider_id: str | None = None):
        pid = provider_id or self.get_active_provider_id()
        return self._providers[pid]

    def provider_info(self, provider_id: str | None = None) -> ProviderInfo | None:
        return get_provider_info(provider_id or self.get_active_provider_id())

    def is_configured(self, provider_id: str | None = None) -> bool:
        return self.provider(provider_id).is_configured()

    def is_connected(self, provider_id: str | None = None) -> bool:
        return self.provider(provider_id).is_connected()

    def connected_account(self, provider_id: str | None = None) -> str:
        return self.provider(provider_id).connected_account()

    def supports_upload(self, provider_id: str | None = None) -> bool:
        info = self.provider_info(provider_id)
        return bool(info and info.supports_upload and self.is_connected(provider_id))

    def get_auth_url(self, provider_id: str, redirect_uri: str | None = None) -> str:
        provider = self.provider(provider_id)
        if redirect_uri is not None:
            return provider.get_auth_url(redirect_uri=redirect_uri)
        return provider.get_auth_url()

    def complete_auth(self, provider_id: str, callback_url: str, redirect_uri: str | None = None) -> str:
        provider = self.provider(provider_id)
        if redirect_uri is not None:
            email = provider.complete_auth(callback_url, redirect_uri=redirect_uri)
        else:
            email = provider.complete_auth(callback_url)
        self.set_active_provider(provider_id)
        return email

    def disconnect(self, provider_id: str | None = None) -> None:
        self.provider(provider_id).disconnect()

    def save_oauth_settings(self, provider_id: str, client_id: str, client_secret: str) -> None:
        client_id = client_id.strip()
        client_secret = client_secret.strip()
        if not client_id or not client_secret:
            raise CloudProviderError("Both fields are required.")
        if provider_id == "google_drive":
            self.store.set_setting("oauth_google_client_id", client_id)
            self.store.set_setting("oauth_google_client_secret", client_secret)
        elif provider_id == "dropbox":
            self.store.set_setting("oauth_dropbox_app_key", client_id)
            self.store.set_setting("oauth_dropbox_app_secret", client_secret)
        elif provider_id == "onedrive":
            self.store.set_setting("oauth_onedrive_client_id", client_id)
            self.store.set_setting("oauth_onedrive_client_secret", client_secret)
        else:
            raise CloudProviderError("This provider does not use OAuth credentials.")

    def oauth_settings_configured(self, provider_id: str) -> bool:
        return self.provider(provider_id).is_configured()

    def create_folder(
        self,
        name: str,
        provider_id: str | None = None,
        folder_url: str = "",
    ) -> CreatedFolder:
        pid = provider_id or self.get_active_provider_id()
        provider = self.provider(pid)
        if pid == "cloud_link":
            return provider.create_folder_from_url(name, folder_url)
        return provider.create_folder(name)

    def upload_file(
        self,
        provider_id: str,
        remote_folder_id: str,
        filename: str,
        content: bytes,
        mime_type: str,
    ) -> RemoteFile:
        return self.provider(provider_id).upload_file(remote_folder_id, filename, content, mime_type)

    def list_files(self, provider_id: str, remote_folder_id: str) -> list[RemoteFile]:
        return self.provider(provider_id).list_files(remote_folder_id)

    def folder_exists(self, provider_id: str, remote_folder_id: str) -> bool:
        if provider_id == "cloud_link":
            return True
        return self.provider(provider_id).folder_exists(remote_folder_id)

    def delete_file(self, provider_id: str, remote_file_id: str) -> None:
        if provider_id == "cloud_link":
            raise CloudProviderError("Delete is not available for manual cloud links.")
        self.provider(provider_id).delete_file(remote_file_id)

    def delete_folder(self, provider_id: str, remote_folder_id: str) -> None:
        provider = self.provider(provider_id)
        if provider_id == "cloud_link":
            return
        provider.delete_folder(remote_folder_id)
