from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from database import DataStore
from version_info import get_app_info, version_tuple

CACHE_SETTING = "update_check_cache"
CACHE_TTL_SECONDS = 6 * 60 * 60
USER_AGENT = "QRFileshare-UpdateCheck/1.0"


@dataclass
class UpdateInfo:
    available: bool
    latest_version: str
    download_url: str
    release_url: str
    release_notes: str = ""


def _normalize_version(tag: str) -> str:
    value = (tag or "").strip()
    if value.lower().startswith("v"):
        value = value[1:]
    return value


def _is_newer(latest: str, current: str) -> bool:
    return version_tuple(latest) > version_tuple(current)


def _github_repo() -> str:
    env_repo = os.getenv("GITHUB_REPO", "").strip()
    if env_repo:
        return env_repo
    info = get_app_info()
    return str(info.get("github_repo", "")).strip()


def _pick_download_url(release: dict) -> tuple[str, str]:
    release_url = str(release.get("html_url", "")).strip()
    download_url = release_url
    for asset in release.get("assets", []):
        name = str(asset.get("name", ""))
        if name.lower().endswith(".exe"):
            download_url = str(asset.get("browser_download_url", download_url)).strip()
            break
    return download_url, release_url


def _fetch_latest_release(repo: str) -> dict:
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    with urlopen(request, timeout=12) as response:
        return json.loads(response.read().decode("utf-8"))


def _load_cache(store: DataStore) -> Optional[UpdateInfo]:
    raw = store.get_setting(CACHE_SETTING, "")
    if not raw:
        return None
    try:
        payload = json.loads(raw)
        checked_at = float(payload.get("checked_at", 0))
        if time.time() - checked_at > CACHE_TTL_SECONDS:
            return None
        return UpdateInfo(
            available=bool(payload.get("available")),
            latest_version=str(payload.get("latest_version", "")),
            download_url=str(payload.get("download_url", "")),
            release_url=str(payload.get("release_url", "")),
            release_notes=str(payload.get("release_notes", "")),
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _save_cache(store: DataStore, info: UpdateInfo) -> None:
    payload = {
        "checked_at": time.time(),
        "available": info.available,
        "latest_version": info.latest_version,
        "download_url": info.download_url,
        "release_url": info.release_url,
        "release_notes": info.release_notes,
    }
    store.set_setting(CACHE_SETTING, json.dumps(payload))


def check_for_update(store: DataStore, *, force: bool = False) -> Optional[UpdateInfo]:
    repo = _github_repo()
    if not repo:
        return None

    if not force:
        cached = _load_cache(store)
        if cached is not None:
            return cached

    current_version = str(get_app_info()["app_version"])
    try:
        release = _fetch_latest_release(repo)
    except (URLError, TimeoutError, json.JSONDecodeError, OSError):
        return _load_cache(store)

    latest_version = _normalize_version(str(release.get("tag_name", "")))
    if not latest_version:
        return None

    download_url, release_url = _pick_download_url(release)
    info = UpdateInfo(
        available=_is_newer(latest_version, current_version),
        latest_version=latest_version,
        download_url=download_url,
        release_url=release_url,
        release_notes=str(release.get("body", "")).strip(),
    )
    _save_cache(store, info)
    return info
