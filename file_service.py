from __future__ import annotations

from cloud_providers.base import CloudProviderError
from cloud_service import CloudService
from database import Folder


def delete_folder_files(
    cloud: CloudService,
    folder: Folder,
    file_ids: list[str],
) -> tuple[int, list[str]]:
    if not file_ids:
        raise ValueError("Select at least one file to delete.")

    provider_info = cloud.provider_info(folder.provider)
    if not provider_info or not provider_info.supports_upload:
        raise ValueError("File delete is not available for this folder type.")

    if not cloud.is_connected(folder.provider):
        raise CloudProviderError(f"Sign in to {provider_info.name} first.")

    try:
        known = {
            remote_file.id: remote_file.name
            for remote_file in cloud.list_files(folder.provider, folder.drive_folder_id)
        }
    except CloudProviderError as exc:
        raise ValueError(str(exc)) from exc

    deleted = 0
    errors: list[str] = []
    for file_id in file_ids:
        name = known.get(file_id)
        if not name:
            errors.append("One or more selected files were not found in this folder.")
            continue
        try:
            cloud.delete_file(folder.provider, file_id)
            deleted += 1
        except CloudProviderError as exc:
            errors.append(f"{name}: {exc}")
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    return deleted, errors
