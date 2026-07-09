import json
from typing import Optional

import msal
import requests

from cloud_providers.base import CloudProviderError, CreatedFolder, RemoteFile
from config import BASE_URL
from database import DataStore

GRAPH = "https://graph.microsoft.com/v1.0"
SCOPES = ["Files.ReadWrite", "User.Read", "offline_access"]


class OneDriveProvider:
    id = "onedrive"
    name = "OneDrive"

    def __init__(self, store: DataStore) -> None:
        self.store = store

    def _credentials(self) -> tuple[str, str]:
        client_id = self.store.get_setting("oauth_onedrive_client_id")
        client_secret = self.store.get_setting("oauth_onedrive_client_secret")
        if client_id and client_secret:
            return client_id, client_secret
        from config import ONEDRIVE_CLIENT_ID, ONEDRIVE_CLIENT_SECRET

        return ONEDRIVE_CLIENT_ID, ONEDRIVE_CLIENT_SECRET

    def is_configured(self) -> bool:
        client_id, client_secret = self._credentials()
        return bool(client_id and client_secret)

    def is_connected(self) -> bool:
        return self.store.get_oauth_token(self.id) is not None

    def connected_account(self) -> str:
        token = self.store.get_oauth_token(self.id)
        return token["email"] if token else ""

    def _redirect_uri(self) -> str:
        return f"{BASE_URL}/auth/onedrive/callback"

    def _app(self) -> msal.ConfidentialClientApplication:
        client_id, client_secret = self._credentials()
        if not client_id or not client_secret:
            raise CloudProviderError("Save OneDrive client ID and secret in Settings first.")
        return msal.ConfidentialClientApplication(
            client_id,
            authority="https://login.microsoftonline.com/common",
            client_credential=client_secret,
        )

    def get_auth_url(self, redirect_uri: str | None = None) -> str:
        app = self._app()
        flow = app.initiate_auth_code_flow(SCOPES, redirect_uri=self._redirect_uri())
        if "auth_uri" not in flow:
            raise CloudProviderError(flow.get("error_description", "Could not start Microsoft sign-in."))
        self.store.set_setting("oauth_onedrive_flow", json.dumps(flow))
        return flow["auth_uri"]

    def complete_auth(self, callback_url: str, redirect_uri: str | None = None) -> str:
        stored = self.store.get_setting("oauth_onedrive_flow")
        if not stored:
            raise CloudProviderError("Microsoft sign-in session expired. Try again.")
        flow = json.loads(stored)
        app = self._app()
        result = app.acquire_token_by_auth_code_flow(flow, auth_response={"url": callback_url})
        if "access_token" not in result:
            raise CloudProviderError(result.get("error_description", "Microsoft sign-in failed."))
        email = self._profile_email(result["access_token"])
        self.store.save_oauth_token(self.id, json.dumps(result), email=email)
        return email

    def disconnect(self) -> None:
        self.store.clear_oauth_token(self.id)

    def _token_payload(self) -> dict:
        token = self.store.get_oauth_token(self.id)
        if not token:
            raise CloudProviderError("Sign in to OneDrive first.")
        return json.loads(token["token_json"])

    def _access_token(self) -> str:
        payload = self._token_payload()
        if payload.get("expires_in", 0) <= 0 or not payload.get("access_token"):
            app = self._app()
            refreshed = app.acquire_token_by_refresh_token(payload.get("refresh_token"), SCOPES)
            if "access_token" not in refreshed:
                raise CloudProviderError("OneDrive session expired. Sign in again.")
            payload.update(refreshed)
            self.store.save_oauth_token(self.id, json.dumps(payload), email=self.connected_account())
        return payload["access_token"]

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token()}"}

    def _profile_email(self, access_token: str) -> str:
        response = requests.get(f"{GRAPH}/me", headers={"Authorization": f"Bearer {access_token}"}, timeout=30)
        if response.ok:
            data = response.json()
            return data.get("mail") or data.get("userPrincipalName", "")
        return ""

    def create_folder(self, name: str) -> CreatedFolder:
        response = requests.post(
            f"{GRAPH}/me/drive/root/children",
            headers=self._headers(),
            json={"name": name, "folder": {}, "@microsoft.graph.conflictBehavior": "rename"},
            timeout=30,
        )
        response.raise_for_status()
        item = response.json()
        link_resp = requests.post(
            f"{GRAPH}/me/drive/items/{item['id']}/createLink",
            headers=self._headers(),
            json={"type": "view", "scope": "anonymous"},
            timeout=30,
        )
        share_url = item.get("webUrl", "")
        if link_resp.ok:
            share_url = link_resp.json().get("link", {}).get("webUrl", share_url)
        return CreatedFolder(remote_id=item["id"], share_url=share_url)

    def delete_folder(self, remote_folder_id: str) -> None:
        response = requests.delete(
            f"{GRAPH}/me/drive/items/{remote_folder_id}",
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()

    def folder_exists(self, remote_folder_id: str) -> bool:
        response = requests.get(
            f"{GRAPH}/me/drive/items/{remote_folder_id}",
            headers=self._headers(),
            timeout=30,
        )
        if response.status_code == 404:
            return False
        if not response.ok:
            raise CloudProviderError(f"Could not check OneDrive folder: {response.text}")
        return True

    def upload_file(self, remote_folder_id: str, filename: str, content: bytes, mime_type: str) -> RemoteFile:
        response = requests.put(
            f"{GRAPH}/me/drive/items/{remote_folder_id}:/{filename}:/content",
            headers={**self._headers(), "Content-Type": mime_type or "application/octet-stream"},
            data=content,
            timeout=120,
        )
        response.raise_for_status()
        item = response.json()
        return RemoteFile(
            id=item["id"],
            name=item["name"],
            size=item.get("size"),
            mime_type=item.get("file", {}).get("mimeType", mime_type),
            web_url=item.get("webUrl", ""),
            modified_at=item.get("lastModifiedDateTime", ""),
        )

    def list_files(self, remote_folder_id: str) -> list[RemoteFile]:
        response = requests.get(
            f"{GRAPH}/me/drive/items/{remote_folder_id}/children",
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()
        files = []
        for item in response.json().get("value", []):
            if "file" not in item:
                continue
            files.append(
                RemoteFile(
                    id=item["id"],
                    name=item["name"],
                    size=item.get("size"),
                    mime_type=item.get("file", {}).get("mimeType", ""),
                    web_url=item.get("webUrl", ""),
                    modified_at=item.get("lastModifiedDateTime", ""),
                )
            )
        return files

    def delete_file(self, remote_file_id: str) -> None:
        response = requests.delete(
            f"{GRAPH}/me/drive/items/{remote_file_id}",
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()
