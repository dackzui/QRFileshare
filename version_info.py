"""Single source of truth for app version and metadata."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_FILE = Path(__file__).resolve()

APP_NAME = "QRFileshare"
APP_VERSION = "1.3.0"
APP_AUTHOR = "Marie Apellanes"
APP_YEAR = 2026
APP_DEVELOPER_URL = "https://apellanes.com.au"
APP_DEVELOPER_LABEL = "Apellanes.com.au"
# Set when published on GitHub, e.g. "your-username/QRFileshare"
GITHUB_REPO = "dackzui/QRFileshare"


def _version_file_path() -> Path:
    if getattr(sys, "frozen", False):
        external = Path(sys.executable).parent / "version_info.py"
        if external.exists():
            return external
    return _PROJECT_FILE


def _load_namespace(path: Path) -> dict:
    namespace: dict = {"__file__": str(path)}
    exec(path.read_text(encoding="utf-8"), namespace)
    return namespace


def get_app_info() -> dict[str, str | int]:
    """Read metadata from version_info.py (reloads on each call)."""
    namespace = _load_namespace(_version_file_path())
    return {
        "app_name": str(namespace.get("APP_NAME", APP_NAME)),
        "app_version": str(namespace.get("APP_VERSION", APP_VERSION)),
        "app_author": str(namespace.get("APP_AUTHOR", APP_AUTHOR)),
        "app_year": int(namespace.get("APP_YEAR", APP_YEAR)),
        "app_developer_url": str(namespace.get("APP_DEVELOPER_URL", APP_DEVELOPER_URL)),
        "app_developer_label": str(namespace.get("APP_DEVELOPER_LABEL", APP_DEVELOPER_LABEL)),
        "github_repo": str(namespace.get("GITHUB_REPO", GITHUB_REPO)),
    }


def version_tuple(version: str | None = None) -> tuple[int, int, int, int]:
    parts = (version or APP_VERSION).split(".")
    numbers = [int(part) for part in parts[:4]]
    while len(numbers) < 4:
        numbers.append(0)
    return numbers[0], numbers[1], numbers[2], numbers[3]


def _read_project_namespace() -> dict:
    return _load_namespace(_PROJECT_FILE)


def sync_build_files(base_dir: Path | None = None) -> None:
    """Update build/installer files from this module."""
    base = base_dir or _PROJECT_FILE.parent
    info = _read_project_namespace()
    name = str(info["APP_NAME"])
    version = str(info["APP_VERSION"])
    author = str(info["APP_AUTHOR"])
    year = int(info["APP_YEAR"])
    file_version = ".".join(str(part) for part in version_tuple(version))

    version_txt = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={version_tuple(version)},
    prodvers={version_tuple(version)},
    mask=0x3F,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          "040904B0",
          [
            StringStruct("CompanyName", "{author}"),
            StringStruct("FileDescription", "{name} Desktop"),
            StringStruct("FileVersion", "{file_version}"),
            StringStruct("InternalName", "{name}"),
            StringStruct("LegalCopyright", "Copyright (C) {year} {author}"),
            StringStruct("OriginalFilename", "{name}.exe"),
            StringStruct("ProductName", "{name}"),
            StringStruct("ProductVersion", "{file_version}"),
          ],
        )
      ]
    ),
    VarFileInfo([VarStruct("Translation", [1033, 1200])]),
  ],
)
"""
    (base / "version_info.txt").write_text(version_txt, encoding="utf-8")

    iss_inc = f"""; Auto-generated from version_info.py — do not edit by hand
#define MyAppName "{name}"
#define MyAppVersion "{version}"
#define MyAppPublisher "{author}"
"""
    (base / "installer" / "version.inc.iss").write_text(iss_inc, encoding="utf-8")

    readme = f"""{name} v{version}
© {year} {author}

Share Google Drive folders with QR codes.

First-time setup
----------------
1. Launch {name} from the Start menu or desktop shortcut.
2. Click "Sign in with Google Drive" and use your normal Google account.
   No API keys or Google Cloud setup is required for end users.
3. Optional: edit .env in the install folder to set BASE_URL to your PC's
   network address (for phone QR scanning), e.g. http://192.168.1.10:5000

Data is stored in:
  data\\       - share links database
  output\\qr\\  - generated QR images

Support
-------
Default share expiry can be changed in the app under Settings.

For the app developer (building the installer)
----------------------------------------------
Place credentials.json in the project folder before running build_installer.bat.
See credentials.json.example for the required format.
"""
    (base / "installer" / "README.txt").write_text(readme, encoding="utf-8")
    print(f"Synced build files for {name} v{version}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync QRFileshare version build files.")
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Update version_info.txt and installer metadata from version_info.py",
    )
    args = parser.parse_args()
    if args.sync:
        sync_build_files()
        return 0
    info = get_app_info()
    print(f"{info['app_name']} v{info['app_version']} © {info['app_year']} {info['app_author']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
