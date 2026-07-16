from dataclasses import dataclass
from datetime import timezone
from pathlib import Path

from database import DataStore, Folder, ShareLink
from expiry import ExpiryError, format_duration, validate_expiry
from qr_generator import build_share_url, default_qr_path, generate_qr_image


@dataclass
class ShareResult:
    link: ShareLink
    share_url: str
    qr_path: Path


def create_share(
    store: DataStore,
    *,
    target_url: str,
    label: str = "",
    folder: Folder | None = None,
    expiry_days: int | None = None,
    expiry_value: int | None = None,
    expiry_unit: str | None = None,
    expiry_duration=None,
    qr_theme: str = "canva-classic",
    qr_logo_path: str = "",
    qr_logo_placement: str = "none",
    qr_border_style: str = "none",
    qr_border_path: str = "",
    base_url: str | None = None,
) -> ShareResult:
    from config import BASE_URL

    if expiry_duration is not None:
        duration = expiry_duration
    elif expiry_value is not None and expiry_unit:
        duration = validate_expiry(expiry_value, expiry_unit)
    elif expiry_days is not None:
        duration = validate_expiry(expiry_days, "days")
    else:
        default_value, default_unit = store.get_default_expiry()
        duration = validate_expiry(default_value, default_unit)

    link = store.create_link(
        target_url=target_url,
        expiry_duration=duration,
        label=label or (folder.name if folder else ""),
        folder_id=folder.id if folder else None,
        qr_theme=qr_theme,
        qr_logo_path=qr_logo_path,
        qr_logo_placement=qr_logo_placement,
        qr_border_style=qr_border_style,
        qr_border_path=qr_border_path,
    )
    share_url = build_share_url(base_url or BASE_URL, link.id)
    qr_path = default_qr_path(link.id)
    generate_qr_image(
        target_url,
        qr_path,
        label=link.label,
        theme=qr_theme,
        logo_path=qr_logo_path or None,
        logo_placement=qr_logo_placement,
        border_style=qr_border_style,
        border_path=qr_border_path or None,
    )
    return ShareResult(link=link, share_url=share_url, qr_path=qr_path)


def format_expiry(link: ShareLink) -> str:
    return link.expires_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def format_time_remaining(link: ShareLink) -> str:
    return link.time_remaining


def format_share_expiry_message(link: ShareLink, *, value: int, unit: str) -> str:
    return (
        f"Share link created. Expires {format_expiry(link)} "
        f"({format_duration(value, unit)})."
    )


def process_expired_shares(store: DataStore, cloud) -> int:
    from cleanup_service import delete_folder
    from cloud_providers.base import CloudProviderError
    from cloud_providers.registry import PROVIDERS
    from qr_generator import default_qr_path

    expired = store.list_expired_active_links()
    if not expired:
        return 0

    folder_ids = {link.folder_id for link in expired if link.folder_id}

    for link in expired:
        store.deactivate_link(link.id)
        qr_path = default_qr_path(link.id)
        if qr_path.exists():
            qr_path.unlink()

    for folder_id in folder_ids:
        if store.list_links(folder_id=folder_id):
            continue

        folder = store.get_folder(folder_id)
        if not folder:
            continue

        provider_info = PROVIDERS.get(folder.provider)
        if (
            provider_info
            and provider_info.supports_sync
            and cloud.is_connected(folder.provider)
        ):
            try:
                cloud.delete_folder(folder.provider, folder.drive_folder_id)
            except CloudProviderError:
                pass
            except Exception:
                pass

        try:
            delete_folder(store, cloud, folder_id, delete_from_cloud=False)
        except ValueError:
            pass

    return len(expired)


def revoke_share(store: DataStore, cloud, link_id: str) -> str:
    from cloud_providers.base import CloudProviderError
    from cloud_providers.registry import PROVIDERS

    link = store.get_link(link_id)
    if not link:
        raise ValueError("Share link not found.")

    folder = store.get_folder(link.folder_id) if link.folder_id else None
    store.deactivate_link(link_id)

    if not folder:
        return "Share revoked."

    provider_info = PROVIDERS.get(folder.provider)
    folder_deleted = False
    if provider_info and provider_info.supports_sync:
        try:
            cloud.delete_folder(folder.provider, folder.drive_folder_id)
            folder_deleted = True
        except CloudProviderError as exc:
            return f"Share revoked, but cloud folder was not deleted: {exc}"
        except Exception as exc:
            return f"Share revoked, but cloud folder was not deleted: {exc}"

    store.deactivate_links_for_folder(folder.id)
    for share in store.list_links(folder_id=folder.id, include_inactive=True):
        qr_path = default_qr_path(share.id)
        if qr_path.exists():
            qr_path.unlink()
    store.delete_folder_record(folder.id)

    if folder_deleted:
        return f'Share revoked and folder "{folder.name}" deleted from {provider_info.name}.'
    return f'Share revoked and folder "{folder.name}" removed from the app.'
