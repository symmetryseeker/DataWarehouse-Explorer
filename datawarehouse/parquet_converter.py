"""
Auto-convert CSV/JSON to Apache Parquet via DuckDB.

Parquet is 5-10x smaller than CSV, supports columnar queries, and is
the standard format for data lakes and analytical workloads.

Usage::

    from datawarehouse.parquet_converter import ParquetConverter

    converter = ParquetConverter()
    converter.csv_to_parquet("data.csv", "data.parquet")
    converter.batch_convert("E:/DataWarehouse/data/structured/csv/")
"""

from __future__ import annotations

import logging
import sys
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb  # auto-installed by duckdb_engine.py

logger = logging.getLogger("DataWarehouse.Parquet")


class ParquetConverter:
    """Convert flat data files to Parquet using DuckDB's native reader/writer.

    DuckDB handles CSV/JSON schema inference, type detection, and compression
    automatically. Parquet output uses ZSTD compression by default.

    Args:
        compression: Parquet compression codec (``"zstd"``, ``"snappy"``, ``"gzip"``).
        row_group_size: Rows per Parquet row group.
    """

    def __init__(self, compression: str = "zstd",
                 row_group_size: int = 100000) -> None:
        self._compression = compression
        self._row_group_size = row_group_size
        self._db = duckdb.connect(":memory:")
        self._stats: Dict[str, Any] = {
            "converted": 0, "skipped": 0, "failed": 0,
            "bytes_saved": 0, "files": [],
        }

    # ------------------------------------------------------------------
    # Single file
    # ------------------------------------------------------------------

    def csv_to_parquet(self, csv_path: Path,
                       output_path: Optional[Path] = None) -> Path:
        """Convert a single CSV to Parquet.

        Args:
            csv_path: Path to .csv file.
            output_path: Optional output path. Default: same dir, .parquet suffix.

        Returns:
            Path to the generated .parquet file.
        """
        if output_path is None:
            output_path = csv_path.with_suffix(".parquet")

        original_size = csv_path.stat().st_size
        self._db.execute(f"""
            COPY (
                SELECT * FROM read_csv_auto('{csv_path}')
            ) TO '{output_path}' (
                FORMAT PARQUET, COMPRESSION '{self._compression}',
                ROW_GROUP_SIZE {self._row_group_size}
            )
        """)
        parquet_size = output_path.stat().st_size
        ratio = (1 - parquet_size / original_size) * 100 if original_size > 0 else 0

        self._stats["converted"] += 1
        self._stats["bytes_saved"] += (original_size - parquet_size)
        self._stats["files"].append({
            "source": str(csv_path),
            "output": str(output_path),
            "original_mb": round(original_size / 1e6, 2),
            "parquet_mb": round(parquet_size / 1e6, 2),
            "compression_ratio": f"{ratio:.0f}%",
        })

        logger.info("CSV → Parquet: %s (%.2f MB → %.2f MB, -%.0f%%)",
                    csv_path.name,
                    original_size / 1e6,
                    parquet_size / 1e6,
                    ratio)
        return output_path

    def json_to_parquet(self, json_path: Path,
                        output_path: Optional[Path] = None) -> Path:
        """Convert a JSON (array of objects) file to Parquet."""
        if output_path is None:
            output_path = json_path.with_suffix(".parquet")

        original_size = json_path.stat().st_size
        self._db.execute(f"""
            COPY (
                SELECT * FROM read_json_auto('{json_path}')
            ) TO '{output_path}' (
                FORMAT PARQUET, COMPRESSION '{self._compression}',
                ROW_GROUP_SIZE {self._row_group_size}
            )
        """)
        parquet_size = output_path.stat().st_size
        ratio = (1 - parquet_size / original_size) * 100 if original_size > 0 else 0

        self._stats["converted"] += 1
        self._stats["bytes_saved"] += (original_size - parquet_size)
        logger.info("JSON → Parquet: %s (%.2f MB → %.2f MB, -%.0f%%)",
                    json_path.name, original_size / 1e6, parquet_size / 1e6, ratio)
        return output_path

    # ------------------------------------------------------------------
    # Batch
    # ------------------------------------------------------------------

    def batch_convert(self, dir_path: Path, pattern: str = "*.csv",
                      output_dir: Optional[Path] = None,
                      delete_original: bool = False) -> Dict[str, Any]:
        """Convert all matching files in a directory to Parquet.

        Args:
            dir_path: Source directory.
            pattern: Glob pattern for source files.
            output_dir: Where to write .parquet files (default: same dir).
            delete_original: If True, delete source files after conversion.

        Returns:
            Conversion statistics dict.
        """
        from pathlib import Path as _Path
        output_dir = output_dir or dir_path
        output_dir.mkdir(parents=True, exist_ok=True)

        # Reset stats
        self._stats = {"converted": 0, "skipped": 0, "failed": 0,
                       "bytes_saved": 0, "files": []}

        for source_file in sorted(dir_path.rglob(pattern)):
            if source_file.suffix.lower() == ".parquet":
                continue  # already converted

            output_file = output_dir / source_file.relative_to(dir_path).with_suffix(".parquet")
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Skip if Parquet already exists and is newer
            if output_file.exists() and output_file.stat().st_mtime > source_file.stat().st_mtime:
                self._stats["skipped"] += 1
                continue

            try:
                if source_file.suffix.lower() == ".csv":
                    self.csv_to_parquet(source_file, output_file)
                elif source_file.suffix.lower() == ".json":
                    self.json_to_parquet(source_file, output_file)
                else:
                    self._stats["skipped"] += 1
                    continue

                if delete_original:
                    source_file.unlink()
            except Exception as exc:
                logger.error("Failed to convert %s: %s", source_file, exc)
                self._stats["failed"] += 1

        return self.stats

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    @property
    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)

    def close(self) -> None:
        self._db.close()
