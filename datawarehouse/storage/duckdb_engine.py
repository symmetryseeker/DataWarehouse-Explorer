"""
DuckDB analytical query engine — fast OLAP on local Parquet/CSV files.

Replaces JSON-file metadata scanning with SQL-powered analytics.
Perfect for personal data analysis: zero-config, in-process, columnar.

Usage::

    from datawarehouse.storage import DuckDBEngine

    engine = DuckDBEngine("E:/DataWarehouse/analytics.db")
    engine.ingest_csv_directory("E:/DataWarehouse/data/structured/csv/")
    result = engine.query("SELECT category, AVG(price) FROM products GROUP BY 1")
"""

from __future__ import annotations

import logging
import re
import sys
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import duckdb
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "duckdb", "--quiet"])
    import duckdb  # type: ignore

logger = logging.getLogger("DataWarehouse.Storage")


class DuckDBEngine:
    """DuckDB-powered analytical query engine.

    Provides:
    - CSV/Parquet ingestion with auto schema detection
    - SQL query interface on all ingested data
    - Export to Parquet/CSV/JSON
    - Hot-data caching layer

    Args:
        db_path: Path to the DuckDB database file.
        read_only: If True, open in read-only mode.
    """

    def __init__(self, db_path: str = ":memory:", read_only: bool = False) -> None:
        self._db_path = db_path
        self._db = duckdb.connect(db_path, read_only=read_only)
        self._tables: set = set()
        logger.info("DuckDB engine initialized: %s", db_path)

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def ingest_csv(self, table_name: str, csv_path: Path) -> int:
        """Register a single CSV as a table.

        Returns row count.
        """
        safe_name = re.sub(r"[^\w]", "_", table_name)
        self._db.execute(
            f'CREATE OR REPLACE TABLE "{safe_name}" AS '
            f"SELECT * FROM read_csv_auto('{csv_path}')"
        )
        count = self._db.execute(f'SELECT COUNT(*) FROM "{safe_name}"').fetchone()[0]
        self._tables.add(safe_name)
        logger.info("Ingested CSV → table '%s': %d rows from %s", safe_name, count, csv_path.name)
        return count

    def ingest_csv_directory(self, dir_path: Path, pattern: str = "*.csv") -> int:
        """Batch ingest all CSVs in a directory.

        Returns total number of files ingested.
        """
        count = 0
        for csv_file in sorted(dir_path.rglob(pattern)):
            try:
                table_name = csv_file.stem
                self.ingest_csv(table_name, csv_file)
                count += 1
            except Exception as exc:
                logger.warning("Failed to ingest %s: %s", csv_file, exc)
        return count

    def ingest_parquet(self, table_name: str, parquet_path: Path) -> int:
        """Register a Parquet file as a table."""
        safe_name = re.sub(r"[^\w]", "_", table_name)
        self._db.execute(
            f'CREATE OR REPLACE TABLE "{safe_name}" AS '
            f"SELECT * FROM read_parquet('{parquet_path}')"
        )
        count = self._db.execute(f'SELECT COUNT(*) FROM "{safe_name}"').fetchone()[0]
        self._tables.add(safe_name)
        return count

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(self, sql: str) -> Dict[str, Any]:
        """Execute a SQL query and return structured results."""
        result = self._db.execute(sql)
        columns = [desc[0] for desc in result.description]
        rows = [list(r) for r in result.fetchall()]
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "sql": sql,
        }

    def query_df(self, sql: str) -> "duckdb.DuckDBPyRelation":
        """Execute SQL and return a DuckDB relation (lazy DataFrame)."""
        return self._db.sql(sql)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_parquet(self, table_name: str, output_path: Path) -> None:
        """Export a table to Parquet format (columnar, compressed)."""
        self._db.execute(
            f'COPY "{table_name}" TO \'{output_path}\' (FORMAT PARQUET)'
        )
        logger.info("Exported '%s' → %s", table_name, output_path)

    def export_csv(self, table_name: str, output_path: Path) -> None:
        """Export a table to CSV."""
        self._db.execute(
            f'COPY "{table_name}" TO \'{output_path}\' (FORMAT CSV, HEADER)'
        )

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def list_tables(self) -> List[Dict[str, Any]]:
        """List all registered tables with row counts."""
        tables = self._db.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='main'"
        ).fetchall()
        result = []
        for (tname,) in tables:
            count = self._db.execute(
                f'SELECT COUNT(*) FROM "{tname}"'
            ).fetchone()[0]
            cols = self._db.execute(f"DESCRIBE \"{tname}\"").fetchall()
            result.append({
                "name": tname,
                "rows": count,
                "columns": [{"name": c[0], "type": c[1]} for c in cols],
            })
        return result

    def table_schema(self, table_name: str) -> Optional[List[Dict[str, str]]]:
        """Get column schema for a table."""
        try:
            cols = self._db.execute(f"DESCRIBE \"{table_name}\"").fetchall()
            return [{"name": c[0], "type": c[1]} for c in cols]
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
