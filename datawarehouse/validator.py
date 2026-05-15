"""Stage 2 — Deep validation and quality scoring for discovered repos."""

from __future__ import annotations

import ast
import csv
import json
import logging
import re
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import RepoMeta, ValidationReport
from .utils import human_size

logger = logging.getLogger("DeepSeek_DataV4")

# Patterns that indicate structured data or API documentation
DATA_FILE_PATTERNS: List[str] = [
    ".json", ".csv", ".xml", ".db", ".sqlite",
    ".parquet", ".feather", ".arrow", ".avro",
]
API_DOC_PATTERNS: List[str] = [
    "swagger.json", "openapi.yaml", "openapi.yml", "openapi.json",
]
README_API_PATTERN: re.Pattern = re.compile(
    r"(https?://[^\s]*api[^\s]*|/api/v?\d|endpoint|REST\s*API|GraphQL)",
    re.IGNORECASE,
)

LICENSE_PATTERNS: Dict[str, List[str]] = {
    "MIT": [r"MIT\s+License", r"Permission is hereby granted, free of charge"],
    "Apache 2.0": [r"Apache\s+License.*2\.0", r"Licensed under the Apache License"],
    "GPL": [r"GNU GENERAL PUBLIC LICENSE", r"GPLv[23]"],
    "CC0": [r"CC0\s+1\.0", r"Creative Commons Zero", r"dedicate.*public domain"],
    "BSD": [r"BSD\s+License", r"Redistribution and use in source and binary forms"],
}

PII_PATTERNS: Dict[str, re.Pattern] = {
    "email": re.compile(r"(email|e\-mail|email_address|contact_email)", re.IGNORECASE),
    "phone": re.compile(r"(phone|telephone|cell|mobile|contact_number|phone_number)", re.IGNORECASE),
    "address": re.compile(r"(address|street|city|state|zip|postal|location|residence)", re.IGNORECASE),
    "name": re.compile(r"(first_name|last_name|full_name|given_name|surname|middle_name)", re.IGNORECASE),
    "ssn": re.compile(r"(ssn|social_security|national_id|tax_id)", re.IGNORECASE),
    "ip": re.compile(r"(ip_address|ip_addr|client_ip|remote_addr)", re.IGNORECASE),
}


class Validator:
    """Assess repository quality by inspecting files, code, and documentation."""

    def __init__(self, warehouse_root: Path) -> None:
        self._root = warehouse_root

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def validate(self, repo_meta: RepoMeta, project_dir: Path) -> RepoMeta:
        """Run all checks against a downloaded repo directory and update scores."""
        score = 0.0

        data_files = self._find_data_files(project_dir)
        repo_meta.data_files = [str(p.relative_to(project_dir)) for p in data_files]
        data_types = list({p.suffix for p in data_files if p.suffix})
        repo_meta.data_types = data_types
        if data_files:
            score += min(len(data_files) * 1.5, 15)

        api_docs = self._find_api_docs(project_dir)
        repo_meta.api_docs_found = api_docs
        if api_docs:
            score += 10

        readme_path = self._find_readme(project_dir)
        if readme_path:
            try:
                content = readme_path.read_text(encoding="utf-8", errors="ignore")
                if README_API_PATTERN.search(content):
                    score += 5
            except OSError:
                pass

        # Deep validation of data files
        for f in data_files:
            suffix = f.suffix.lower()
            if suffix == ".csv":
                report = self._validate_csv(f)
                if report.valid:
                    score += 2
            elif suffix == ".xml":
                report = self._validate_xml(f)
                if report.valid:
                    score += 1
            elif suffix in (".db", ".sqlite"):
                report = self._validate_sqlite(f)
                if report.valid and report.tables > 0:
                    score += 3

        # Validate Python / JSON for structural correctness
        valid_count = 0
        for f in project_dir.rglob("*.py"):
            if self._validate_python(f):
                valid_count += 1
        for f in project_dir.rglob("*.json"):
            if self._validate_json(f):
                valid_count += 1
        score += min(valid_count * 0.5, 10)

        # Dataset sample bonus
        for pat in ["sample*", "example*", "test*", "demo*", "data*"]:
            if list(project_dir.glob(pat)):
                score += 3
                break

        # README bonus
        if readme_path:
            size = readme_path.stat().st_size
            if size > 500:
                score += 3
            if size > 2000:
                score += 2

        # License detection
        license_type = self._detect_license(project_dir)
        if license_type:
            repo_meta.license = license_type
            repo_meta.license_file_path = self._find_license_path(project_dir)
            score += 2

        repo_meta.quality_score = round(score, 1)
        repo_meta.structure_summary = self._build_summary(repo_meta, project_dir)
        return repo_meta

    # ------------------------------------------------------------------
    # Deep validation methods (Phase 1)
    # ------------------------------------------------------------------

    def _validate_csv(self, path: Path) -> ValidationReport:
        """Validate CSV structure: column consistency, null ratios, date formats."""
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                reader = csv.reader(f)
                headers = next(reader, [])
                if not headers:
                    return ValidationReport(
                        file_path=str(path), file_type="csv",
                        valid=False, error="No headers found")

                col_count = len(headers)
                null_counts = [0] * col_count
                date_col_indices: List[int] = []
                total_rows = 0
                inconsistent_rows = 0

                date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
                col_samples: Dict[int, List[str]] = {i: [] for i in range(col_count)}

                for row in reader:
                    total_rows += 1
                    if len(row) != col_count:
                        inconsistent_rows += 1
                    for i, cell in enumerate(row[:col_count]):
                        if cell.strip() == "":
                            null_counts[i] += 1
                        if i in col_samples and len(col_samples[i]) < 20:
                            col_samples[i].append(cell.strip())

                # Date format detection per column
                for i in range(col_count):
                    samples = col_samples[i]
                    if samples and len(samples) >= 3:
                        matches = sum(1 for s in samples if date_pattern.match(s))
                        if matches / len(samples) >= 0.7:
                            date_col_indices.append(i)

                null_ratios = {
                    headers[i]: round(null_counts[i] / max(total_rows, 1), 3)
                    for i in range(col_count)
                }

                return ValidationReport(
                    file_path=str(path), file_type="csv", valid=True,
                    headers=headers, total_rows=total_rows,
                    inconsistent_rows=inconsistent_rows,
                    null_ratios=null_ratios,
                    date_columns=date_col_indices,
                )
        except Exception as exc:
            return ValidationReport(
                file_path=str(path), file_type="csv",
                valid=False, error=str(exc))

    def _validate_xml(self, path: Path) -> ValidationReport:
        """Validate XML well-formedness and count unique elements."""
        try:
            tree = ET.parse(str(path))
            root_tag = tree.getroot().tag
            elements: set = set()
            for el in tree.iter():
                elements.add(el.tag)
            return ValidationReport(
                file_path=str(path), file_type="xml", valid=True,
                root_tag=root_tag, unique_elements=len(elements))
        except ET.ParseError as exc:
            return ValidationReport(
                file_path=str(path), file_type="xml",
                valid=False, error=str(exc))

    def _validate_sqlite(self, path: Path) -> ValidationReport:
        """Inspect SQLite structure via PRAGMA table_info."""
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            cursor = conn.cursor()
            tables = cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            schema: Dict[str, Any] = {}
            for (tname,) in tables:
                cols = cursor.execute(f"PRAGMA table_info('{tname}')").fetchall()
                schema[tname] = [{"name": c[1], "type": c[2]} for c in cols]
            conn.close()
            return ValidationReport(
                file_path=str(path), file_type="sqlite", valid=True,
                tables=len(tables), schema=schema)
        except Exception as exc:
            return ValidationReport(
                file_path=str(path), file_type="sqlite",
                valid=False, error=str(exc))

    # ------------------------------------------------------------------
    # PII scanning (Phase 4)
    # ------------------------------------------------------------------

    def scan_pii(self, file_path: Path) -> Dict[str, List[str]]:
        """Scan CSV headers for potential PII (personally identifiable info)."""
        findings: Dict[str, List[str]] = {}
        if file_path.suffix.lower() != ".csv":
            return findings
        try:
            with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
                reader = csv.reader(f)
                headers = next(reader, [])
            for header in headers:
                for pii_type, pattern in PII_PATTERNS.items():
                    if pattern.search(header):
                        findings.setdefault(pii_type, []).append(header)
        except Exception:
            pass
        return findings

    # ------------------------------------------------------------------
    # License detection (Phase 1)
    # ------------------------------------------------------------------

    def _detect_license(self, project_dir: Path) -> Optional[str]:
        """Scan LICENSE files to identify the license type."""
        for fname in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"):
            lic_path = project_dir / fname
            if lic_path.exists():
                try:
                    content = lic_path.read_text(encoding="utf-8", errors="ignore")[:2000]
                    for lic_type, patterns in LICENSE_PATTERNS.items():
                        for pat in patterns:
                            if re.search(pat, content, re.IGNORECASE):
                                return lic_type
                except OSError:
                    continue
        return None

    @staticmethod
    def _find_license_path(project_dir: Path) -> Optional[str]:
        for fname in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"):
            lic_path = project_dir / fname
            if lic_path.exists():
                return str(lic_path.relative_to(project_dir))
        return None

    # ------------------------------------------------------------------
    # File discovery utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _find_data_files(root: Path) -> List[Path]:
        found: List[Path] = []
        for pat in DATA_FILE_PATTERNS:
            try:
                found.extend(root.rglob(f"*{pat}"))
            except OSError:
                continue
        return list({p.resolve() for p in found})

    @staticmethod
    def _find_api_docs(root: Path) -> bool:
        for pat in API_DOC_PATTERNS:
            try:
                if list(root.rglob(pat)):
                    return True
            except OSError:
                continue
        return False

    @staticmethod
    def _find_readme(root: Path) -> Optional[Path]:
        for name in ("README.md", "README.rst", "README.txt", "README"):
            candidate = root / name
            if candidate.exists():
                return candidate
        for p in root.iterdir():
            if p.is_file() and p.name.lower().startswith("readme"):
                return p
        return None

    # ------------------------------------------------------------------
    # Syntax validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_python(path: Path) -> bool:
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
            ast.parse(source)
            return True
        except (SyntaxError, OSError, MemoryError):
            return False

    @staticmethod
    def _validate_json(path: Path) -> bool:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                json.load(f)
            return True
        except (json.JSONDecodeError, OSError):
            return False

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    @staticmethod
    def _build_summary(meta: RepoMeta, project_dir: Path) -> str:
        parts: List[str] = []
        parts.append(f"Language: {meta.language or 'unknown'}")
        parts.append(f"Stars: {meta.stars}")
        if meta.data_types:
            parts.append(f"Data types: {', '.join(meta.data_types)}")
        if meta.data_files:
            parts.append(f"Data files ({len(meta.data_files)}): {', '.join(meta.data_files[:5])}")
        if meta.api_docs_found:
            parts.append("API docs: yes")
        if meta.license:
            parts.append(f"License: {meta.license}")
        parts.append(f"Quality score: {meta.quality_score}/50")
        try:
            total = sum(1 for _ in project_dir.rglob("*") if _.is_file())
            parts.append(f"Total files: {total}")
        except OSError:
            pass
        return " | ".join(parts)
