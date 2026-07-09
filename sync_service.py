from __future__ import annotations

from cloud_providers.base import CloudProviderError
from cloud_providers.registry import PROVIDERS
from cleanup_service import delete_folder, delete_share_only
from cloud_service import CloudService
from database import DataStore
from share_service import process_expired_shares


def refresh_from_cloud(store: DataStore, cloud: CloudService) -> str:
    expired_count = process_expired_shares(store, cloud)
    removed_folders: list[str] = []
    removed_share_count = 0
    errors: list[str] = []

    for folder in list(store.list_folders()):
        provider_info = PROVIDERS.get(folder.provider)
        if not provider_info or not provider_info.supports_sync:
            continue
        if not cloud.is_connected(folder.provider):
            continue

        try:
            exists = cloud.folder_exists(folder.provider, folder.drive_folder_id)
        except CloudProviderError as exc:
            errors.append(f"{folder.name}: {exc}")
            continue

        if exists:
            continue

        share_count = len(store.list_links(folder_id=folder.id))
        delete_folder(store, cloud, folder.id, delete_from_cloud=False)
        removed_folders.append(folder.name)
        removed_share_count += share_count

    for share in list(store.list_links()):
        if share.folder_id and not store.get_folder(share.folder_id):
            delete_share_only(store, share.id)
            removed_share_count += 1

    if errors and not removed_folders and not removed_share_count and not expired_count:
        raise ValueError(errors[0])

    parts: list[str] = []
    if removed_folders:
        preview = ", ".join(removed_folders[:5])
        if len(removed_folders) > 5:
            preview += "…"
        parts.append(
            f"removed {len(removed_folders)} folder{'s' if len(removed_folders) != 1 else ''} "
            f"no longer in cloud ({preview})"
        )
    if removed_share_count:
        parts.append(
            f"removed {removed_share_count} related share{'s' if removed_share_count != 1 else ''}"
        )
    if expired_count:
        parts.append(f"expired {expired_count} share{'s' if expired_count != 1 else ''}")

    if not parts:
        message = "Everything is already up to date with cloud storage."
    else:
        message = "Refresh complete: " + "; ".join(parts) + "."

    if errors:
        message += f" Could not check {len(errors)} folder(s) — sign in and try again."

    return message
