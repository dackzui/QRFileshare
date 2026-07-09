import json
import os
from typing import Any, Optional

os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from cloud_providers.base import CloudProviderError, CreatedFolder, RemoteFile
from config import BASE_URL, GOOGLE_CREDENTIALS_FILE, GOOGLE_SCOPES
from database import DataStore


class GoogleDriveProvider:
    id = "google_drive"
    name = "Google Drive"

    def __init__(self, store: DataStore) -> None:
        self.store = store

    def _credentials(self) -> tuple[str, str]:
        client_id = self.store.get_setting("oauth_google_client_id")
        client_secret = self.store.get_setting("oauth_google_client_secret")
        if client_id and client_secret:
            return client_id, client_secret
        from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

        if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
            return GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
        if GOOGLE_CREDENTIALS_FILE.exists():
            with GOOGLE_CREDENTIALS_FILE.open(encoding="utf-8") as handle:
                data = json.load(handle)
            web = data.get("web") or data.get("installed") or {}
            return web.get("client_id", ""), web.get("client_secret", "")
        return "", ""

    def is_configured(self) -> bool:
        client_id, client_secret = self._credentials()
        return bool(client_id and client_secret)

    def is_connected(self) -> bool:
        return self._load_credentials() is not None

    def connected_account(self) -> str:
        token = self.store.get_oauth_token(self.id)
        return token["email"] if token else ""

    def _redirect_uri(self, override: str | None = None) -> str:
        if override:
            return override.rstrip("/")
        stored = self.store.get_setting("oauth_google_redirect_uri")
        if stored:
            return stored
        return f"{BASE_URL.rstrip('/')}/auth/google_drive/callback"

    def _client_config(self, redirect_uri: str) -> dict[str, Any]:
        client_id, client_secret = self._credentials()
        if not client_id or not client_secret:
            raise CloudProviderError(
                "Google Drive sign-in is not available in this build. "
                "Contact the app publisher."
            )
        return {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        }

    def get_auth_url(self, redirect_uri: str | None = None) -> str:
        uri = self._redirect_uri(redirect_uri)
        self.store.set_setting("oauth_google_redirect_uri", uri)
        flow = Flow.from_client_config(
            self._client_config(uri),
            scopes=GOOGLE_SCOPES,
            redirect_uri=uri,
        )
        auth_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        self.store.set_setting("oauth_pending_state", state or "")
        if flow.code_verifier:
            self.store.set_setting("oauth_google_code_verifier", flow.code_verifier)
        return auth_url

    def complete_auth(self, callback_url: str, redirect_uri: str | None = None) -> str:
        uri = self._redirect_uri(redirect_uri)
        pending_state = self.store.get_setting("oauth_pending_state")
        code_verifier = self.store.get_setting("oauth_google_code_verifier")
        flow = Flow.from_client_config(
            self._client_config(uri),
            scopes=GOOGLE_SCOPES,
            redirect_uri=uri,
            state=pending_state or None,
            code_verifier=code_verifier or None,
            autogenerate_code_verifier=not bool(code_verifier),
        )
        flow.fetch_token(authorization_response=callback_url)
        credentials = flow.credentials
        email = self._email_from_credentials(credentials)
        self.store.save_oauth_token(self.id, credentials.to_json(), email=email)
        self.store.set_setting("oauth_pending_state", "")
        self.store.set_setting("oauth_google_code_verifier", "")
        return email

    def disconnect(self) -> None:
        self.store.clear_oauth_token(self.id)

    def _email_from_credentials(self, credentials: Credentials) -> str:
        if credentials.id_token:
            try:
                from google.auth.transport import requests as google_requests
                from google.oauth2 import id_token as google_id_token

                info = google_id_token.verify_oauth2_token(
                    credentials.id_token,
                    google_requests.Request(),
                    credentials.client_id,
                )
                return info.get("email", "")
            except Exception:
                pass
        return self.connected_account() or "Google account"

    def _load_credentials(self) -> Optional[Credentials]:
        token = self.store.get_oauth_token(self.id)
        if not token:
            return None
        credentials = Credentials.from_authorized_user_info(
            json.loads(token["token_json"])
        )
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            self.store.save_oauth_token(self.id, credentials.to_json(), email=token.get("email", ""))
        if not credentials.valid:
            return None
        return credentials

    def _service(self):
        credentials = self._load_credentials()
        if not credentials:
            raise CloudProviderError("Sign in to Google Drive first.")
        return build("drive", "v3", credentials=credentials, cache_discovery=False)

    def create_folder(self, name: str) -> CreatedFolder:
        service = self._service()
        folder = (
            service.files()
            .create(body={"name": name, "mimeType": "application/vnd.google-apps.folder"}, fields="id, webViewLink")
            .execute()
        )
        service.permissions().create(
            fileId=folder["id"],
            body={"type": "anyone", "role": "reader"},
        ).execute()
        return CreatedFolder(
            remote_id=folder["id"],
            share_url=folder.get("webViewLink", f"https://drive.google.com/drive/folders/{folder['id']}"),
        )

    def delete_folder(self, remote_folder_id: str) -> None:
        service = self._service()
        service.files().delete(fileId=remote_folder_id).execute()

    def folder_exists(self, remote_folder_id: str) -> bool:
        from googleapiclient.errors import HttpError

        service = self._service()
        try:
            item = (
                service.files()
                .get(fileId=remote_folder_id, fields="id,trashed")
                .execute()
            )
        except HttpError as exc:
            if exc.resp.status == 404:
                return False
            raise CloudProviderError(f"Could not check Google Drive folder: {exc}") from exc
        return not item.get("trashed", False)

    def upload_file(self, remote_folder_id: str, filename: str, content: bytes, mime_type: str) -> RemoteFile:
        import io

        service = self._service()
        media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mime_type, resumable=False)
        created = (
            service.files()
            .create(
                body={"name": filename, "parents": [remote_folder_id]},
                media_body=media,
                fields="id, name, webViewLink, mimeType, size, modifiedTime",
            )
            .execute()
        )
        return RemoteFile(
            id=created["id"],
            name=created["name"],
            size=int(created.get("size", 0) or 0),
            mime_type=created.get("mimeType", ""),
            web_url=created.get("webViewLink", ""),
            modified_at=created.get("modifiedTime", ""),
        )

    def list_files(self, remote_folder_id: str) -> list[RemoteFile]:
        service = self._service()
        query = f"'{remote_folder_id}' in parents and trashed = false"
        result = (
            service.files()
            .list(
                q=query,
                fields="files(id, name, mimeType, size, modifiedTime, webViewLink)",
                orderBy="folder,name",
            )
            .execute()
        )
        return [
            RemoteFile(
                id=item["id"],
                name=item["name"],
                size=int(item.get("size", 0) or 0),
                mime_type=item.get("mimeType", ""),
                web_url=item.get("webViewLink", ""),
                modified_at=item.get("modifiedTime", ""),
            )
            for item in result.get("files", [])
        ]

    def delete_file(self, remote_file_id: str) -> None:
        service = self._service()
        service.files().delete(fileId=remote_file_id).execute()
