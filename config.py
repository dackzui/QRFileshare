import os
import sys
from pathlib import Path

from dotenv import load_dotenv

if getattr(sys, "frozen", False):
    RESOURCE_DIR = Path(sys._MEIPASS)
    APP_DIR = Path(sys.executable).parent
else:
    RESOURCE_DIR = Path(__file__).resolve().parent
    APP_DIR = RESOURCE_DIR

load_dotenv(APP_DIR / ".env")


def _resolve_app_path(env_key: str, default: Path) -> Path:
    raw = os.getenv(env_key)
    if not raw:
        return default
    path = Path(raw)
    if not path.is_absolute():
        path = APP_DIR / path
    return path

# Desktop app uses http://localhost for OAuth — required by oauthlib for local sign-in
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

BASE_DIR = RESOURCE_DIR

BASE_URL = os.getenv("BASE_URL", "http://localhost:5000").rstrip("/")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() in ("1", "true", "yes")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-change-me-in-production")

DEFAULT_EXPIRY_DAYS = int(os.getenv("DEFAULT_EXPIRY_DAYS", "30"))
DATABASE_PATH = _resolve_app_path("DATABASE_PATH", APP_DIR / "data" / "links.db")
QR_OUTPUT_DIR = _resolve_app_path("QR_OUTPUT_DIR", APP_DIR / "output" / "qr")
GOOGLE_CREDENTIALS_FILE = _resolve_app_path(
    "GOOGLE_CREDENTIALS_FILE", APP_DIR / "credentials.json"
)
# Embedded in the .exe when built with credentials.json present
if getattr(sys, "frozen", False):
    _embedded_creds = RESOURCE_DIR / "credentials.json"
    if _embedded_creds.exists():
        GOOGLE_CREDENTIALS_FILE = _embedded_creds

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
DROPBOX_APP_KEY = os.getenv("DROPBOX_APP_KEY", "")
DROPBOX_APP_SECRET = os.getenv("DROPBOX_APP_SECRET", "")
ONEDRIVE_CLIENT_ID = os.getenv("ONEDRIVE_CLIENT_ID", "")
ONEDRIVE_CLIENT_SECRET = os.getenv("ONEDRIVE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI", f"{BASE_URL}/auth/google_drive/callback"
)

MIN_EXPIRY_MINUTES = 1
MIN_EXPIRY_DAYS = 1
MAX_EXPIRY_DAYS = 365

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

QR_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
