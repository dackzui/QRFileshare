"""Backward-compatible shim — use cloud_service.CloudService instead."""

from cloud_providers.base import CloudProviderError as GoogleDriveError
from cloud_providers.google_drive import GoogleDriveProvider as GoogleDriveService

__all__ = ["GoogleDriveError", "GoogleDriveService"]
