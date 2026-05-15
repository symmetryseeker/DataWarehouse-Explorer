"""Shared fixtures for DataWarehouse tests."""

from __future__ import annotations

import csv
import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Dict, Generator

import pytest


@pytest.fixture
def temp_warehouse() -> Generator[Path, None, None]:
    """Create a temporary warehouse directory structure."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for d in ["metadata", "code", "raw", "processed", "data/structured/csv",
                   "data/structured/json", "tmp", "logs"]:
            (root / d).mkdir(parents=True, exist_ok=True)
        yield root


@pytest.fixture
def sample_csv_file(temp_warehouse: Path) -> Path:
    """Create a valid sample CSV with dates and some nulls."""
    path = temp_warehouse / "sample.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "value", "category"])
        writer.writerow(["2024-01-01", "10", "A"])
        writer.writerow(["2024-01-02", "20", "B"])
        writer.writerow(["2024-01-03", "", "A"])  # null value
        writer.writerow(["invalid", "30", "C"])    # invalid date
    return path


@pytest.fixture
def sample_csv_inconsistent(temp_warehouse: Path) -> Path:
    """Create a CSV with inconsistent column counts."""
    path = temp_warehouse / "inconsistent.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["a", "b", "c"])
        writer.writerow(["1", "2", "3"])
        writer.writerow(["1", "2"])  # missing column
    return path


@pytest.fixture
def sample_json_file(temp_warehouse: Path) -> Path:
    """Create a valid JSON file."""
    path = temp_warehouse / "sample.json"
    path.write_text(json.dumps({"key": "value", "list": [1, 2, 3]}))
    return path


@pytest.fixture
def sample_sqlite_db(temp_warehouse: Path) -> Path:
    """Create a sample SQLite database with two tables."""
    path = temp_warehouse / "sample.db"
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE users (id INTEGER, name TEXT)")
    conn.execute("CREATE TABLE orders (id INTEGER, user_id INTEGER, amount REAL)")
    conn.execute("INSERT INTO users VALUES (1, 'Alice')")
    conn.execute("INSERT INTO orders VALUES (1, 1, 99.99)")
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def sample_project_dir(temp_warehouse: Path) -> Path:
    """Create a minimal project directory with LICENSE and README."""
    proj = temp_warehouse / "code" / "test-project"
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "README.md").write_text("# Test Project\n\nThis is a test.")
    (proj / "LICENSE").write_text("MIT License\n\nPermission is hereby granted, free of charge...")
    (proj / "data.csv").write_text("name,age\nAlice,30\nBob,25\n")
    return proj


@pytest.fixture
def sample_meta() -> Dict[str, Any]:
    """Return a sample RepoMeta dict."""
    return {
        "repo_name": "test/data",
        "repo_url": "https://github.com/test/data",
        "mirror_name": "direct_seed",
        "description": "A test dataset",
        "stars": 100,
        "language": "Python",
        "tags": ["test", "dataset"],
        "data_files": ["data.csv"],
        "data_types": [".csv"],
        "quality_score": 10.0,
    }
