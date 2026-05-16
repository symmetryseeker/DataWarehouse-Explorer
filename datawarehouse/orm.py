"""
SQLAlchemy ORM layer — replace raw SQL metadb.py with proper ORM.

Provides:
- Declarative models for repositories, data files, licenses, tasks
- Session factory with connection pooling
- Automatic migration from legacy JSON metadata
- O(log N) indexed queries for web UI search

Usage::

    from datawarehouse.orm import get_session, Repository, DataFile
    session = get_session()
    repos = session.query(Repository).filter(Repository.tags.contains("csv")).all()
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Text, DateTime,
    ForeignKey, Index, create_engine, event,
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship,
    sessionmaker, Session,
)

# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Repository(Base):
    """Indexed repository metadata — replaces metadata/*.json files."""

    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    repo_name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    repo_url: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    mirror_name: Mapped[Optional[str]] = mapped_column(String(64))
    description: Mapped[Optional[str]] = mapped_column(Text)
    description_ai: Mapped[Optional[str]] = mapped_column(Text)  # LLM-generated summary
    stars: Mapped[int] = mapped_column(Integer, default=0, index=True)
    language: Mapped[Optional[str]] = mapped_column(String(64))
    tags: Mapped[Optional[str]] = mapped_column(Text)  # JSON array string
    data_types: Mapped[Optional[str]] = mapped_column(Text)  # JSON array string
    quality_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    commit_recency_days: Mapped[Optional[int]] = mapped_column(Integer)  # days since last commit
    license_type: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    license_file_path: Mapped[Optional[str]] = mapped_column(String(512))
    local_path: Mapped[Optional[str]] = mapped_column(String(1024))
    structure_summary: Mapped[Optional[str]] = mapped_column(Text)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    files: Mapped[List["DataFile"]] = relationship(back_populates="repository", cascade="all, delete-orphan")
    licenses: Mapped[List["License"]] = relationship(back_populates="repository", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_repo_score_stars", "quality_score", "stars"),
        Index("idx_repo_tags", "tags"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "repo_name": self.repo_name,
            "repo_url": self.repo_url,
            "description": self.description,
            "description_ai": self.description_ai,
            "stars": self.stars,
            "language": self.language,
            "tags": json.loads(self.tags) if self.tags else [],
            "data_types": json.loads(self.data_types) if self.data_types else [],
            "quality_score": self.quality_score,
            "commit_recency_days": self.commit_recency_days,
            "license": self.license_type,
            "license_file_path": self.license_file_path,
            "local_path": self.local_path,
            "structure_summary": self.structure_summary,
            "ingested_at": self.ingested_at.isoformat() if self.ingested_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "slug": self.repo_name.replace("/", "_").lower(),
        }


class DataFile(Base):
    """Per-file metadata with content-addressable dedup support."""

    __tablename__ = "data_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_uuid: Mapped[str] = mapped_column(String(36), ForeignKey("repositories.uuid", ondelete="CASCADE"), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_name: Mapped[str] = mapped_column(String(256), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    suffix: Mapped[Optional[str]] = mapped_column(String(16), index=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_path: Mapped[Optional[str]] = mapped_column(String(1024))
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_status: Mapped[Optional[str]] = mapped_column(Text)  # JSON
    pii_flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    pii_fields: Mapped[Optional[str]] = mapped_column(Text)  # JSON array
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationship
    repository: Mapped["Repository"] = relationship(back_populates="files")

    __table_args__ = (
        Index("idx_file_sha256_name", "sha256", "file_name", unique=True),
    )


class License(Base):
    """Detected license records per repository."""

    __tablename__ = "licenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_uuid: Mapped[str] = mapped_column(String(36), ForeignKey("repositories.uuid", ondelete="CASCADE"), nullable=False, index=True)
    license_type: Mapped[str] = mapped_column(String(64), nullable=False)
    license_text_snippet: Mapped[Optional[str]] = mapped_column(Text)
    license_file_path: Mapped[Optional[str]] = mapped_column(String(512))

    repository: Mapped["Repository"] = relationship(back_populates="licenses")


class DownloadTask(Base):
    """Celery-compatible task tracking table for async downloads."""

    __tablename__ = "download_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    repo_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    repo_name: Mapped[Optional[str]] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)  # pending/running/done/failed
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


# ---------------------------------------------------------------------------
# Engine & Session Factory
# ---------------------------------------------------------------------------

_engine = None
_SessionLocal = None


def init_db(db_path: str = "sqlite:///warehouse.db", echo: bool = False) -> None:
    """Initialize the database engine and create all tables.

    Args:
        db_path: SQLAlchemy database URL. Examples:
                 ``"sqlite:///E:/DataWarehouse/warehouse.db"``
                 ``"postgresql://user:pass@localhost/datawarehouse"``
        echo: If True, log all SQL statements.
    """
    global _engine, _SessionLocal
    _engine = create_engine(
        db_path,
        echo=echo,
        connect_args={"check_same_thread": False} if "sqlite" in db_path else {},
        pool_size=5,
        max_overflow=10,
    )
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)

    # Enable WAL mode for SQLite (better concurrent read performance)
    if "sqlite" in db_path:
        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

    Base.metadata.create_all(_engine)


def get_session() -> Session:
    """Get a new database session. Caller is responsible for closing it.

    Usage::

        with get_session() as session:
            repo = session.query(Repository).first()
    """
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _SessionLocal()


def get_db_path_from_warehouse(warehouse_root: Path) -> str:
    """Derive the SQLite DB path from the warehouse root."""
    db_file = warehouse_root / "warehouse.db"
    return f"sqlite:///{db_file}"


# ---------------------------------------------------------------------------
# Migration from legacy JSON metadata
# ---------------------------------------------------------------------------

def migrate_json_to_orm(metadata_dir: Path, session: Session) -> int:
    """One-shot migration: legacy metadata/*.json → SQLAlchemy ORM.

    Args:
        metadata_dir: Directory containing ``*.json`` metadata files.
        session: Active SQLAlchemy session.

    Returns:
        Number of repositories migrated.
    """
    if not metadata_dir.is_dir():
        return 0

    count = 0
    for mf in sorted(metadata_dir.glob("*.json")):
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
            existing = session.query(Repository).filter(
                Repository.repo_url == data.get("repo_url", "")
            ).first()
            if existing:
                continue

            repo = Repository(
                repo_name=data.get("repo_name", mf.stem),
                repo_url=data.get("repo_url", ""),
                mirror_name=data.get("mirror_name", ""),
                description=data.get("description", ""),
                stars=data.get("stars", 0),
                language=data.get("language", ""),
                tags=json.dumps(data.get("tags", [])),
                data_types=json.dumps(data.get("data_types", [])),
                quality_score=data.get("quality_score", 0.0),
                license_type=data.get("license"),
                license_file_path=data.get("license_file_path"),
                local_path=data.get("local_path", ""),
                structure_summary=data.get("structure_summary", ""),
                ingested_at=datetime.fromisoformat(data["ingested_at"]) if data.get("ingested_at") else None,
                updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
            )
            session.add(repo)
            count += 1
        except (json.JSONDecodeError, KeyError, OSError) as exc:
            import logging
            logging.getLogger("DataWarehouse.ORM").warning("Migration skip '%s': %s", mf.name, exc)

    session.commit()

    # Backup old JSON
    backup_dir = metadata_dir.parent / "metadata_json_backup"
    backup_dir.mkdir(exist_ok=True)
    for mf in metadata_dir.glob("*.json"):
        try:
            mf.rename(backup_dir / mf.name)
        except OSError:
            pass

    return count
