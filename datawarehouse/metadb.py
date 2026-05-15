"""SQLite metadata database — scalable replacement for JSON metadata files."""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import RepoMeta
from .utils import now_iso

logger = logging.getLogger("DeepSeek_DataV4")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS repositories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid TEXT UNIQUE NOT NULL,
    repo_name TEXT NOT NULL,
    repo_url TEXT UNIQUE NOT NULL,
    mirror_name TEXT,
    description TEXT,
    stars INTEGER DEFAULT 0,
    language TEXT,
    tags TEXT,
    quality_score REAL DEFAULT 0.0,
    structure_summary TEXT,
    license TEXT,
    license_file_path TEXT,
    local_path TEXT,
    ingested_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS data_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_uuid TEXT NOT NULL REFERENCES repositories(uuid),
    file_path TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_size INTEGER,
    suffix TEXT,
    sha256 TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    is_processed INTEGER DEFAULT 0,
    validation_status TEXT,
    pii_flagged INTEGER DEFAULT 0,
    pii_fields TEXT,
    ingested_at TEXT,
    UNIQUE(sha256, file_name)
);

CREATE TABLE IF NOT EXISTS licenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_uuid TEXT NOT NULL REFERENCES repositories(uuid),
    license_type TEXT NOT NULL,
    license_text_snippet TEXT,
    license_file_path TEXT
);

CREATE INDEX IF NOT EXISTS idx_repos_name ON repositories(repo_name);
CREATE INDEX IF NOT EXISTS idx_repos_score ON repositories(quality_score);
CREATE INDEX IF NOT EXISTS idx_repos_license ON repositories(license);
CREATE INDEX IF NOT EXISTS idx_files_sha256 ON data_files(sha256);
CREATE INDEX IF NOT EXISTS idx_files_repo ON data_files(repo_uuid);
CREATE INDEX IF NOT EXISTS idx_files_suffix ON data_files(suffix);
"""


class MetaDatabase:
    """SQLite-backed metadata store with content-addressable file tracking."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()

    # --- Repo CRUD ---

    def upsert_repo(self, meta: RepoMeta) -> str:
        """Insert or update a repository record. Returns the UUID."""
        existing = self.get_repo_by_url(meta.repo_url)
        if existing:
            repo_uuid = existing["uuid"]
            self._conn.execute(
                """UPDATE repositories SET quality_score=?, license=?, updated_at=?
                   WHERE uuid=?""",
                (meta.quality_score, meta.license, now_iso(), repo_uuid),
            )
        else:
            repo_uuid = str(uuid.uuid4())
            self._conn.execute(
                """INSERT INTO repositories
                   (uuid, repo_name, repo_url, mirror_name, description, stars,
                    language, tags, quality_score, structure_summary, license,
                    license_file_path, local_path, ingested_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (repo_uuid, meta.repo_name, meta.repo_url, meta.mirror_name,
                 meta.description, meta.stars, meta.language,
                 json.dumps(meta.tags), meta.quality_score,
                 meta.structure_summary, meta.license, meta.license_file_path,
                 meta.local_path, meta.ingested_at or now_iso(), now_iso()),
            )
        self._conn.commit()
        return repo_uuid

    def get_repo_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            "SELECT * FROM repositories WHERE repo_url=?", (url,)
        ).fetchone()
        if row:
            return dict(row)
        return None

    def list_all_repos(self) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM repositories ORDER BY quality_score DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    # --- File CRUD ---

    def add_file_record(self, repo_uuid: str, file_path: str, file_name: str,
                        file_size: int, suffix: str, sha256: str,
                        storage_path: str, pii_flagged: bool = False,
                        pii_fields: Optional[str] = None) -> None:
        self._conn.execute(
            """INSERT OR IGNORE INTO data_files
               (repo_uuid, file_path, file_name, file_size, suffix, sha256,
                storage_path, pii_flagged, pii_fields, ingested_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (repo_uuid, file_path, file_name, file_size, suffix, sha256,
             storage_path, int(pii_flagged), pii_fields, now_iso()),
        )
        self._conn.commit()

    def file_exists(self, sha256: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM data_files WHERE sha256=?", (sha256,)
        ).fetchone()
        return row is not None

    # --- License CRUD ---

    def add_license(self, repo_uuid: str, license_type: str,
                    snippet: str = "", file_path: str = "") -> None:
        self._conn.execute(
            """INSERT OR IGNORE INTO licenses
               (repo_uuid, license_type, license_text_snippet, license_file_path)
               VALUES (?,?,?,?)""",
            (repo_uuid, license_type, snippet[:500], file_path),
        )
        self._conn.commit()

    def license_summary(self) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            """SELECT r.repo_name, r.repo_url, l.license_type
               FROM repositories r
               LEFT JOIN licenses l ON r.uuid = l.repo_uuid
               ORDER BY r.quality_score DESC"""
        ).fetchall()
        return [{"repo_name": r[0], "repo_url": r[1], "license": r[2] or "Unknown"} for r in rows]


def migrate_json_to_sqlite(metadata_dir: Path, db_path: Path) -> int:
    """One-shot migration: JSON metadata files → SQLite. Returns count."""
    if not metadata_dir.is_dir():
        return 0

    db = MetaDatabase(db_path)
    count = 0

    for mf in sorted(metadata_dir.glob("*.json")):
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
            meta = RepoMeta.from_dict(data)
            db.upsert_repo(meta)
            count += 1
        except (json.JSONDecodeError, OSError, TypeError) as exc:
            logger.warning("Migration skip '%s': %s", mf.name, exc)

    # Backup old JSON files
    backup_dir = metadata_dir.parent / "metadata_json_backup"
    backup_dir.mkdir(exist_ok=True)
    for mf in metadata_dir.glob("*.json"):
        try:
            mf.rename(backup_dir / mf.name)
        except OSError:
            pass

    logger.info("Migration complete: %d repos → SQLite at %s", count, db_path)
    db.close()
    return count
