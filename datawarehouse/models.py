"""Core data models for the DataWarehouse pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class RepoMeta:
    """Canonical metadata record for one ingested repository."""

    repo_name: str
    repo_url: str
    mirror_name: str
    description: str = ""
    stars: int = 0
    language: str = ""
    tags: List[str] = field(default_factory=list)
    data_files: List[str] = field(default_factory=list)
    data_types: List[str] = field(default_factory=list)
    api_docs_found: bool = False
    quality_score: float = 0.0
    structure_summary: str = ""
    license: Optional[str] = None
    license_file_path: Optional[str] = None
    local_path: str = ""
    metadata_path: str = ""
    ingested_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RepoMeta":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class FileRecord:
    """Per-file metadata stored in the content-addressable system."""

    repo_uuid: str
    file_path: str
    file_name: str
    file_size: int
    suffix: str
    sha256: str
    storage_path: str
    is_processed: bool = False
    validation_status: Optional[str] = None  # JSON string
    pii_flagged: bool = False
    pii_fields: Optional[str] = None  # JSON array string
    ingested_at: str = ""


@dataclass
class DataPassport:
    """Extended metadata for a dataset — its 'identity document'."""

    uuid: str
    source_repo: str
    source_url: str
    data_domain: str = "unknown"
    update_frequency: str = "unknown"
    license: Optional[str] = None
    license_file_path: Optional[str] = None
    citation: Optional[str] = None
    compatible_tools: List[str] = field(default_factory=list)
    file_count: int = 0
    total_size_bytes: int = 0
    content_hash: str = ""
    version_commit_hash: Optional[str] = None
    ingested_at: str = ""
    updated_at: str = ""


@dataclass
class ValidationReport:
    """Detailed result of validating a single data file."""

    file_path: str
    file_type: str
    valid: bool
    error: Optional[str] = None
    headers: Optional[List[str]] = None
    total_rows: int = 0
    inconsistent_rows: int = 0
    null_ratios: Optional[Dict[str, float]] = None
    date_columns: Optional[List[int]] = None
    tables: int = 0
    schema: Optional[Dict[str, Any]] = None
    unique_elements: int = 0
    root_tag: Optional[str] = None
    pii_findings: Optional[Dict[str, List[str]]] = None
