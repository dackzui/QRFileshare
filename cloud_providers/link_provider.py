from cloud_providers.base import CloudProviderError, CreatedFolder, RemoteFile


class CloudLinkProvider:
    """QR sharing for any pasted cloud folder URL — no API sync."""

    id = "cloud_link"
    name = "Other cloud link"

    def is_configured(self) -> bool:
        return True

    def is_connected(self) -> bool:
        return True

    def connected_account(self) -> str:
        return "Manual link"

    def get_auth_url(self, redirect_uri: str | None = None) -> str:
        raise CloudProviderError("This provider does not use sign-in.")

    def complete_auth(self, callback_url: str, redirect_uri: str | None = None) -> str:
        raise CloudProviderError("This provider does not use sign-in.")

    def disconnect(self) -> None:
        return None

    def create_folder(self, name: str) -> CreatedFolder:
        raise CloudProviderError("Provide a folder URL when creating a cloud link folder.")

    def create_folder_from_url(self, name: str, url: str) -> CreatedFolder:
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            raise CloudProviderError("Enter a valid folder URL.")
        return CreatedFolder(remote_id=url, share_url=url)

    def delete_folder(self, remote_folder_id: str) -> None:
        return None

    def folder_exists(self, remote_folder_id: str) -> bool:
        return True

    def upload_file(self, remote_folder_id: str, filename: str, content: bytes, mime_type: str) -> RemoteFile:
        raise CloudProviderError("Upload is not available for manual cloud links.")

    def delete_file(self, remote_file_id: str) -> None:
        raise CloudProviderError("Delete is not available for manual cloud links.")

    def list_files(self, remote_folder_id: str) -> list[RemoteFile]:
        return []
