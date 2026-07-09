from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass
class CreatedFolder:
    remote_id: str
    share_url: str


@dataclass
class RemoteFile:
    id: str
    name: str
    size: Optional[int]
    mime_type: str
    web_url: str
    modified_at: str = ""


class CloudProviderError(Exception):
    pass


class CloudProvider(Protocol):
    id: str
    name: str

    def is_configured(self) -> bool: ...
    def is_connected(self) -> bool: ...
    def connected_account(self) -> str: ...
    def get_auth_url(self) -> str: ...
    def complete_auth(self, callback_url: str) -> str: ...
    def disconnect(self) -> None: ...
    def create_folder(self, name: str) -> CreatedFolder: ...
    def delete_folder(self, remote_folder_id: str) -> None: ...
    def folder_exists(self, remote_folder_id: str) -> bool: ...
    def upload_file(self, remote_folder_id: str, filename: str, content: bytes, mime_type: str) -> RemoteFile: ...
    def delete_file(self, remote_file_id: str) -> None: ...
    def list_files(self, remote_folder_id: str) -> list[RemoteFile]: ...
