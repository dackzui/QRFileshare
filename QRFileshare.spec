# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
base = Path(SPECPATH)

webview_datas = collect_data_files("webview")
webview_hidden = collect_submodules("webview")

datas = [
    ("templates", "templates"),
    ("static", "static"),
    (".env.example", "."),
    *webview_datas,
]
if (base / "credentials.json").exists():
    datas.append(("credentials.json", "."))

a = Analysis(
    ["main.py"],
    pathex=[str(base)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "cloud_service",
        "cloud_providers",
        "cloud_providers.google_drive",
        "cloud_providers.dropbox_provider",
        "cloud_providers.onedrive_provider",
        "cloud_providers.link_provider",
        "cloud_providers.registry",
        "oauth_bundled",
        "email_compose",
        "cleanup_service",
        "file_service",
        "sync_service",
        "expiry",
        "share_service",
        "qr_generator",
        "update_check",
        "google_auth_oauthlib",
        "googleapiclient",
        "googleapiclient.discovery",
        "google.oauth2.credentials",
        "dropbox",
        "msal",
        "requests",
        "webview",
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
        "clr",
        *webview_hidden,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="QRFileshare",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version="version_info.txt",
)
