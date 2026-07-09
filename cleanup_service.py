from __future__ import annotations

from datetime import date, datetime, time, timezone

from cloud_providers.base import CloudProviderError
from cloud_providers.registry import PROVIDERS
from database import DataStore
from qr_generator import default_qr_path


def date_range_bounds(from_date: date, to_date: date) -> tuple[datetime, datetime]:
    if from_date > to_date:
        raise ValueError("Start date must be on or before end date.")
    local_tz = datetime.now().astimezone().tzinfo
    start = datetime.combine(from_date, time.min, tzinfo=local_tz).astimezone(timezone.utc)
    end = datetime.combine(to_date, time.max, tzinfo=local_tz).astimezone(timezone.utc)
    return start, end


def parse_date_field(value: str, field_name: str) -> date:
    raw = (value or "").strip()
    if not raw:
        raise ValueError(f"{field_name} is required.")
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD.") from exc


def _remove_qr(link_id: str) -> None:
    qr_path = default_qr_path(link_id)
    if qr_path.exists():
        qr_path.unlink()


def delete_share_only(store: DataStore, link_id: str) -> str:
    link = store.get_link(link_id)
    if not link:
        raise ValueError("Share not found.")

    label = link.label or link.id
    _remove_qr(link_id)
    store.delete_link(link_id)
    return f'Share "{label}" deleted.'


def delete_folder(
    store: DataStore,
    cloud,
    folder_id: str,
    *,
    delete_from_cloud: bool = False,
    remove_associated_shares: bool = True,
) -> str:
    folder = store.get_folder(folder_id)
    if not folder:
        raise ValueError("Folder not found.")

    provider_info = PROVIDERS.get(folder.provider)
    cloud_deleted = False
    if delete_from_cloud and provider_info and provider_info.supports_sync:
        try:
            cloud.delete_folder(folder.provider, folder.drive_folder_id)
            cloud_deleted = True
        except CloudProviderError as exc:
            return f'Folder removed from the app, but cloud delete failed: {exc}'
        except Exception as exc:
            return f'Folder removed from the app, but cloud delete failed: {exc}'

    if remove_associated_shares:
        for share in store.list_links(folder_id=folder.id, include_inactive=True):
            _remove_qr(share.id)
            store.delete_link(share.id)

    store.delete_folder_record(folder.id)

    if cloud_deleted and provider_info:
        return f'Folder "{folder.name}" deleted from the app and {provider_info.name}.'
    return f'Folder "{folder.name}" deleted from the app.'


def bulk_delete_by_date(
    store: DataStore,
    cloud,
    *,
    from_date: date,
    to_date: date,
    delete_folders: bool,
    delete_shares: bool,
    delete_from_cloud: bool,
) -> str:
    if not delete_folders and not delete_shares:
        raise ValueError("Choose folders, active shares, or both.")

    start, end = date_range_bounds(from_date, to_date)
    folder_count = 0
    share_count = 0

    if delete_folders:
        for folder in store.list_folders_between(start, end):
            message = delete_folder(
                store,
                cloud,
                folder.id,
                delete_from_cloud=delete_from_cloud,
                remove_associated_shares=False,
            )
            if message.startswith("Folder removed from the app, but cloud delete failed"):
                return message
            folder_count += 1

    if delete_shares:
        cloud_folders_deleted: set[str] = set()
        for link in store.list_links_between(start, end, active_only=True):
            if not store.get_link(link.id):
                continue
            delete_share_only(store, link.id)
            share_count += 1

            if not delete_from_cloud or not link.folder_id:
                continue
            if link.folder_id in cloud_folders_deleted:
                continue

            folder = store.get_folder(link.folder_id)
            if not folder:
                continue

            provider_info = PROVIDERS.get(folder.provider)
            if not provider_info or not provider_info.supports_sync:
                continue

            try:
                cloud.delete_folder(folder.provider, folder.drive_folder_id)
                cloud_folders_deleted.add(link.folder_id)
            except CloudProviderError as exc:
                return (
                    f"Deleted {share_count} active share{'s' if share_count != 1 else ''}, "
                    f"but cloud delete failed for \"{folder.name}\": {exc}"
                )
            except Exception as exc:
                return (
                    f"Deleted {share_count} active share{'s' if share_count != 1 else ''}, "
                    f"but cloud delete failed for \"{folder.name}\": {exc}"
                )

    parts: list[str] = []
    if delete_folders:
        parts.append(f"{folder_count} folder{'s' if folder_count != 1 else ''}")
    if delete_shares:
        parts.append(f"{share_count} active share{'s' if share_count != 1 else ''}")

    if not parts or (folder_count == 0 and share_count == 0):
        return (
            f"No matching folders or active shares found between "
            f"{from_date.isoformat()} and {to_date.isoformat()}."
        )

    summary = " and ".join(parts)
    return f"Deleted {summary} created from {from_date.isoformat()} to {to_date.isoformat()}."
