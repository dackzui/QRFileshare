import json
import secrets
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Optional

from config import DATABASE_PATH, DEFAULT_EXPIRY_DAYS


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _from_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


@dataclass
class ShareLink:
    id: str
    target_url: str
    label: str
    folder_id: Optional[str]
    created_at: datetime
    expires_at: datetime
    is_active: bool
    qr_theme: str = "canva-classic"

    @property
    def is_expired(self) -> bool:
        return _utc_now() >= self.expires_at

    @property
    def is_available(self) -> bool:
        return self.is_active and not self.is_expired

    @property
    def days_remaining(self) -> int:
        delta = self.expires_at - _utc_now()
        return max(0, delta.days)

    @property
    def time_remaining(self) -> str:
        from expiry import format_expiry_duration

        return format_expiry_duration(self.expires_at)


@dataclass
class Folder:
    id: str
    name: str
    provider: str
    drive_folder_id: str
    drive_url: str
    created_at: datetime


class DataStore:
    def __init__(self, db_path: Path = DATABASE_PATH) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS share_links (
                    id TEXT PRIMARY KEY,
                    target_url TEXT NOT NULL,
                    label TEXT NOT NULL DEFAULT '',
                    folder_id TEXT,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    qr_theme TEXT NOT NULL DEFAULT 'canva-classic'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS folders (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    drive_folder_id TEXT NOT NULL,
                    drive_url TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_tokens (
                    provider TEXT PRIMARY KEY,
                    token_json TEXT NOT NULL,
                    email TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._migrate_oauth_tokens(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            self._ensure_column(conn, "share_links", "folder_id", "TEXT")
            self._ensure_column(conn, "share_links", "qr_theme", "TEXT NOT NULL DEFAULT 'canva-classic'")
            self._ensure_column(conn, "folders", "provider", "TEXT NOT NULL DEFAULT 'google_drive'")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_share_links_expires_at ON share_links(expires_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_share_links_folder_id ON share_links(folder_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_folders_created_at ON folders(created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_share_links_created_at ON share_links(created_at)"
            )
            conn.execute(
                "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
                ("default_expiry_days", str(DEFAULT_EXPIRY_DAYS)),
            )
            conn.execute(
                "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
                ("active_cloud_provider", "google_drive"),
            )

    def _migrate_oauth_tokens(self, conn: sqlite3.Connection) -> None:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(oauth_tokens)")}
        if "id" in columns and "provider" not in columns:
            rows = conn.execute("SELECT token_json, email, updated_at FROM oauth_tokens WHERE id = 1").fetchall()
            conn.execute("DROP TABLE oauth_tokens")
            conn.execute(
                """
                CREATE TABLE oauth_tokens (
                    provider TEXT PRIMARY KEY,
                    token_json TEXT NOT NULL,
                    email TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            for row in rows:
                conn.execute(
                    "INSERT INTO oauth_tokens (provider, token_json, email, updated_at) VALUES (?, ?, ?, ?)",
                    ("google_drive", row["token_json"], row["email"], row["updated_at"]),
                )

    def _ensure_column(
        self, conn: sqlite3.Connection, table: str, column: str, definition: str
    ) -> None:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def get_setting(self, key: str, default: str = "") -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO app_settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def get_default_expiry_days(self) -> int:
        raw = self.get_setting("default_expiry_days", str(DEFAULT_EXPIRY_DAYS))
        return int(raw)

    def get_default_expiry(self) -> tuple[int, str]:
        unit = self.get_setting("default_expiry_unit", "")
        if unit in ("minutes", "hours", "days"):
            raw = self.get_setting("default_expiry_value", str(DEFAULT_EXPIRY_DAYS))
            try:
                return int(raw), unit
            except ValueError:
                pass
        return self.get_default_expiry_days(), "days"

    def set_default_expiry(self, value: int, unit: str) -> None:
        self.set_setting("default_expiry_value", str(value))
        self.set_setting("default_expiry_unit", unit)
        if unit == "days":
            self.set_setting("default_expiry_days", str(value))

    def get_email_sender_name(self) -> str:
        return self.get_setting("email_sender_name", "").strip()

    def get_email_intro_text(self) -> str:
        return self.get_setting("email_intro_text", "").strip()

    def set_email_preferences(self, sender_name: str, intro_text: str) -> None:
        self.set_setting("email_sender_name", sender_name.strip())
        self.set_setting("email_intro_text", intro_text.strip())

    def save_oauth_token(self, provider: str, token_json: str, email: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO oauth_tokens (provider, token_json, email, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(provider) DO UPDATE SET
                    token_json = excluded.token_json,
                    email = excluded.email,
                    updated_at = excluded.updated_at
                """,
                (provider, token_json, email, _to_iso(_utc_now())),
            )

    def get_oauth_token(self, provider: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT token_json, email FROM oauth_tokens WHERE provider = ?",
                (provider,),
            ).fetchone()
        if not row:
            return None
        return {"token_json": row["token_json"], "email": row["email"] or ""}

    def clear_oauth_token(self, provider: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM oauth_tokens WHERE provider = ?", (provider,))

    def create_folder(
        self,
        name: str,
        drive_folder_id: str,
        drive_url: str,
        provider: str = "google_drive",
    ) -> Folder:
        folder_id = secrets.token_urlsafe(8)
        created_at = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO folders (id, name, provider, drive_folder_id, drive_url, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (folder_id, name, provider, drive_folder_id, drive_url, _to_iso(created_at)),
            )
        return Folder(
            id=folder_id,
            name=name,
            provider=provider,
            drive_folder_id=drive_folder_id,
            drive_url=drive_url,
            created_at=created_at,
        )

    def _row_to_folder(self, row: sqlite3.Row) -> Folder:
        return Folder(
            id=row["id"],
            name=row["name"],
            provider=row["provider"] if "provider" in row.keys() else "google_drive",
            drive_folder_id=row["drive_folder_id"],
            drive_url=row["drive_url"],
            created_at=_from_iso(row["created_at"]),
        )

    def get_folder(self, folder_id: str) -> Optional[Folder]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM folders WHERE id = ?", (folder_id,)).fetchone()
        return self._row_to_folder(row) if row else None

    def list_folders(self) -> list[Folder]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM folders ORDER BY created_at DESC").fetchall()
        return [self._row_to_folder(row) for row in rows]

    def _row_to_link(self, row: sqlite3.Row) -> ShareLink:
        return ShareLink(
            id=row["id"],
            target_url=row["target_url"],
            label=row["label"] or "",
            folder_id=row["folder_id"],
            created_at=_from_iso(row["created_at"]),
            expires_at=_from_iso(row["expires_at"]),
            is_active=bool(row["is_active"]),
            qr_theme=row["qr_theme"] or "canva-classic",
        )

    def create_link(
        self,
        target_url: str,
        expiry_days: int | None = None,
        *,
        expiry_duration: timedelta | None = None,
        label: str = "",
        folder_id: Optional[str] = None,
        qr_theme: str = "canva-classic",
    ) -> ShareLink:
        link_id = secrets.token_urlsafe(8)
        created_at = _utc_now()
        if expiry_duration is not None:
            expires_at = created_at + expiry_duration
        elif expiry_days is not None:
            expires_at = created_at + timedelta(days=expiry_days)
        else:
            raise ValueError("Either expiry_days or expiry_duration is required.")

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO share_links
                    (id, target_url, label, folder_id, created_at, expires_at, is_active, qr_theme)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    link_id,
                    target_url,
                    label,
                    folder_id,
                    _to_iso(created_at),
                    _to_iso(expires_at),
                    qr_theme,
                ),
            )

        return ShareLink(
            id=link_id,
            target_url=target_url,
            label=label,
            folder_id=folder_id,
            created_at=created_at,
            expires_at=expires_at,
            is_active=True,
            qr_theme=qr_theme,
        )

    def get_link(self, link_id: str) -> Optional[ShareLink]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM share_links WHERE id = ?", (link_id,)).fetchone()
        return self._row_to_link(row) if row else None

    def list_links(
        self, include_inactive: bool = False, folder_id: Optional[str] = None
    ) -> list[ShareLink]:
        clauses = []
        params: list = []
        if not include_inactive:
            clauses.append("is_active = 1")
        if folder_id:
            clauses.append("folder_id = ?")
            params.append(folder_id)
        query = "SELECT * FROM share_links"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_link(row) for row in rows]

    def deactivate_link(self, link_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE share_links SET is_active = 0 WHERE id = ?", (link_id,)
            )
        return cursor.rowcount > 0

    def deactivate_links_for_folder(self, folder_id: str) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE share_links SET is_active = 0 WHERE folder_id = ? AND is_active = 1",
                (folder_id,),
            )
        return cursor.rowcount

    def delete_folder_record(self, folder_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
        return cursor.rowcount > 0

    def delete_link(self, link_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM share_links WHERE id = ?", (link_id,))
        return cursor.rowcount > 0

    def list_folders_between(self, start: datetime, end: datetime) -> list[Folder]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM folders
                WHERE created_at >= ? AND created_at <= ?
                ORDER BY created_at DESC
                """,
                (_to_iso(start), _to_iso(end)),
            ).fetchall()
        return [self._row_to_folder(row) for row in rows]

    def list_links_between(
        self,
        start: datetime,
        end: datetime,
        *,
        active_only: bool = False,
    ) -> list[ShareLink]:
        clauses = ["created_at >= ?", "created_at <= ?"]
        params: list = [_to_iso(start), _to_iso(end)]
        if active_only:
            clauses.append("is_active = 1")
        query = f"SELECT * FROM share_links WHERE {' AND '.join(clauses)} ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_link(row) for row in rows]

    def list_expired_active_links(self) -> list[ShareLink]:
        now = _to_iso(_utc_now())
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM share_links
                WHERE is_active = 1 AND expires_at <= ?
                ORDER BY expires_at ASC
                """,
                (now,),
            ).fetchall()
        return [self._row_to_link(row) for row in rows]

    def deactivate_expired(self) -> int:
        now = _to_iso(_utc_now())
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE share_links
                SET is_active = 0
                WHERE is_active = 1 AND expires_at <= ?
                """,
                (now,),
            )
        return cursor.rowcount


# Backward-compatible alias
LinkStore = DataStore
