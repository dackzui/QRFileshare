import json
from typing import Optional
from urllib.parse import urlencode

import requests

from cloud_providers.base import CloudProviderError, CreatedFolder, RemoteFile
from config import BASE_URL
from database import DataStore


class DropboxProvider:
    id = "dropbox"
    name = "Dropbox"

    AUTH_URL = "https://www.dropbox.com/oauth2/authorize"
    TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
    API_RPC = "https://api.dropboxapi.com/2"
    API_CONTENT = "https://content.dropboxapi.com/2"

    def __init__(self, store: DataStore) -> None:
        self.store = store

    def _app_credentials(self) -> tuple[str, str]:
        key = self.store.get_setting("oauth_dropbox_app_key")
        secret = self.store.get_setting("oauth_dropbox_app_secret")
        if key and secret:
            return key, secret
        from config import DROPBOX_APP_KEY, DROPBOX_APP_SECRET

        return DROPBOX_APP_KEY, DROPBOX_APP_SECRET

    def is_configured(self) -> bool:
        key, secret = self._app_credentials()
        return bool(key and secret)

    def is_connected(self) -> bool:
        return self.store.get_oauth_token(self.id) is not None

    def connected_account(self) -> str:
        token = self.store.get_oauth_token(self.id)
        return token["email"] if token else ""

    def _redirect_uri(self) -> str:
        return f"{BASE_URL}/auth/dropbox/callback"

    def get_auth_url(self, redirect_uri: str | None = None) -> str:
        key, _ = self._app_credentials()
        if not key:
            raise CloudProviderError("Save Dropbox app key and secret in Settings first.")
        params = urlencode(
            {
                "client_id": key,
                "response_type": "code",
                "redirect_uri": self._redirect_uri(),
                "token_access_type": "offline",
            }
        )
        return f"{self.AUTH_URL}?{params}"

    def complete_auth(self, callback_url: str, redirect_uri: str | None = None) -> str:
        from urllib.parse import parse_qs, urlparse

        code = parse_qs(urlparse(callback_url).query).get("code", [None])[0]
        if not code:
            raise CloudProviderError("Dropbox sign-in was cancelled.")
        key, secret = self._app_credentials()
        response = requests.post(
            self.TOKEN_URL,
            data={
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": self._redirect_uri(),
                "client_id": key,
                "client_secret": secret,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        email = self._current_account(payload["access_token"])
        self.store.save_oauth_token(self.id, json.dumps(payload), email=email)
        return email

    def disconnect(self) -> None:
        self.store.clear_oauth_token(self.id)

    def _token_payload(self) -> dict:
        token = self.store.get_oauth_token(self.id)
        if not token:
            raise CloudProviderError("Sign in to Dropbox first.")
        return json.loads(token["token_json"])

    def _access_token(self) -> str:
        payload = self._token_payload()
        if payload.get("refresh_token"):
            key, secret = self._app_credentials()
            response = requests.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": payload["refresh_token"],
                    "client_id": key,
                    "client_secret": secret,
                },
                timeout=30,
            )
            if response.ok:
                refreshed = response.json()
                payload.update(refreshed)
                self.store.save_oauth_token(
                    self.id,
                    json.dumps(payload),
                    email=self.connected_account(),
                )
        return payload["access_token"]

    def _rpc(self, endpoint: str, payload: Optional[dict] = None) -> dict:
        response = requests.post(
            f"{self.API_RPC}/{endpoint}",
            headers={
                "Authorization": f"Bearer {self._access_token()}",
                "Content-Type": "application/json",
            },
            json=payload or {},
            timeout=30,
        )
        response.raise_for_status()
        return response.json() if response.content else {}

    def _current_account(self, access_token: str) -> str:
        response = requests.post(
            f"{self.API_RPC}/users/get_current_account",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
        if response.ok:
            return response.json().get("email", "")
        return ""

    def create_folder(self, name: str) -> CreatedFolder:
        result = self._rpc("files/create_folder_v2", {"path": f"/{name}", "autorename": True})
        metadata = result["metadata"]
        shared = self._rpc(
            "sharing/create_shared_link_with_settings",
            {"path": metadata["path_lower"], "settings": {"requested_visibility": "public"}},
        )
        return CreatedFolder(remote_id=metadata["path_lower"], share_url=shared.get("url", ""))

    def delete_folder(self, remote_folder_id: str) -> None:
        self._rpc("files/delete_v2", {"path": remote_folder_id})

    def folder_exists(self, remote_folder_id: str) -> bool:
        response = requests.post(
            f"{self.API_RPC}/files/get_metadata",
            headers={
                "Authorization": f"Bearer {self._access_token()}",
                "Content-Type": "application/json",
            },
            json={"path": remote_folder_id},
            timeout=30,
        )
        if response.status_code == 409:
            error = response.json().get("error", {})
            if error.get(".tag") == "path" and error.get("path", {}).get(".tag") == "not_found":
                return False
        if response.status_code == 404:
            return False
        if not response.ok:
            raise CloudProviderError(f"Could not check Dropbox folder: {response.text}")
        return True

    def upload_file(self, remote_folder_id: str, filename: str, content: bytes, mime_type: str) -> RemoteFile:
        folder_meta = self._rpc("files/get_metadata", {"path": remote_folder_id})
        path = f"{folder_meta['path_lower'].rstrip('/')}/{filename}"
        response = requests.post(
            f"{self.API_CONTENT}/files/upload",
            headers={
                "Authorization": f"Bearer {self._access_token()}",
                "Content-Type": "application/octet-stream",
                "Dropbox-API-Arg": json.dumps({"path": path, "mode": "add", "autorename": True}),
            },
            data=content,
            timeout=120,
        )
        response.raise_for_status()
        meta = response.json()
        return RemoteFile(
            id=meta["id"],
            name=meta["name"],
            size=meta.get("size"),
            mime_type=mime_type,
            web_url="",
            modified_at=meta.get("client_modified", ""),
        )

    def list_files(self, remote_folder_id: str) -> list[RemoteFile]:
        folder_meta = self._rpc("files/get_metadata", {"path": remote_folder_id})
        result = self._rpc("files/list_folder", {"path": folder_meta["path_lower"]})
        files = []
        for entry in result.get("entries", []):
            if entry.get(".tag") != "file":
                continue
            files.append(
                RemoteFile(
                    id=entry["id"],
                    name=entry["name"],
                    size=entry.get("size"),
                    mime_type="",
                    web_url="",
                    modified_at=entry.get("client_modified", ""),
                )
            )
        return files

    def delete_file(self, remote_file_id: str) -> None:
        self._rpc("files/delete_v2", {"path": f"id:{remote_file_id}"})
