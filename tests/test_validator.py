"""Tests for the Validator module."""

from __future__ import annotations

from pathlib import Path

import pytest

from datawarehouse.validator import Validator
from datawarehouse.models import RepoMeta


def test_validate_csv_structure(sample_csv_file: Path):
    v = Validator(Path("/tmp"))
    report = v._validate_csv(sample_csv_file)
    assert report.valid
    assert report.headers == ["date", "value", "category"]
    assert report.total_rows == 4
    assert report.inconsistent_rows == 0
    assert report.null_ratios is not None
    assert report.null_ratios["value"] == pytest.approx(0.25, abs=0.01)


def test_validate_csv_inconsistent(sample_csv_inconsistent: Path):
    v = Validator(Path("/tmp"))
    report = v._validate_csv(sample_csv_inconsistent)
    assert report.valid
    assert report.inconsistent_rows == 1


def test_validate_json(sample_json_file: Path):
    v = Validator(Path("/tmp"))
    assert v._validate_json(sample_json_file) is True


def test_validate_json_invalid(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text("{invalid")
    v = Validator(Path("/tmp"))
    assert v._validate_json(bad) is False


def test_validate_sqlite(sample_sqlite_db: Path):
    v = Validator(Path("/tmp"))
    report = v._validate_sqlite(sample_sqlite_db)
    assert report.valid
    assert report.tables == 2
    assert "users" in report.schema
    assert "orders" in report.schema


def test_detect_license(sample_project_dir: Path):
    v = Validator(Path("/tmp"))
    lic = v._detect_license(sample_project_dir)
    assert lic == "MIT"


def test_detect_license_none(tmp_path: Path):
    v = Validator(Path("/tmp"))
    lic = v._detect_license(tmp_path)
    assert lic is None


def test_scan_pii(sample_csv_file: Path):
    # CSV has "date","value","category" — no PII
    v = Validator(Path("/tmp"))
    findings = v.scan_pii(sample_csv_file)
    assert findings == {}


def test_scan_pii_email(tmp_path: Path):
    import csv
    path = tmp_path / "pii.csv"
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "email_address", "phone", "last_name", "ip_address"])
        writer.writerow(["1", "a@b.com", "123", "Smith", "10.0.0.1"])
    v = Validator(Path("/tmp"))
    findings = v.scan_pii(path)
    assert "email" in findings
    assert "phone" in findings
    assert "name" in findings      # last_name matches the 'name' PII pattern
    assert "ip" in findings        # ip_address matches the 'ip' PII pattern


def test_validate_updates_repo_meta(sample_project_dir: Path):
    v = Validator(Path("/tmp"))
    meta = RepoMeta(
        repo_name="test/project", repo_url="https://github.com/test/project",
        mirror_name="direct_seed", description="Test",
    )
    result = v.validate(meta, sample_project_dir)
    assert result.quality_score > 0
    assert result.license == "MIT"
    assert result.data_types is not None


