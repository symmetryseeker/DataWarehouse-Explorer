"""
Structured API data loader using dlt (Data Load Tool).

dlt provides: incremental loading, schema evolution, automatic normalization,
and destination-agnostic output (DuckDB, Postgres, Parquet, etc.)

Usage::

    from datawarehouse.ingestion import DLTLoader

    loader = DLTLoader(destination="duckdb")
    loader.load_rest_api(
        "https://api.example.com/data",
        table_name="api_data",
    )
"""

from __future__ import annotations

import logging
import sys
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import dlt  # type: ignore
except ImportError:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "dlt[duckdb]", "--quiet"]
    )
    import dlt  # type: ignore

logger = logging.getLogger("DataWarehouse.Ingestion")


class DLTLoader:
    """dlt-based data loader with incremental loading and schema evolution.

    Args:
        destination: Target destination (``"duckdb"``, ``"postgres"``, ``"bigquery"``,
                     ``"filesystem"``, ``"motherduck"``).
        dataset_name: Logical dataset name for organizing tables.
        pipeline_dir: Directory for dlt pipeline state and schemas.
    """

    VALID_DESTINATIONS = {
        "duckdb", "postgres", "bigquery", "filesystem",
        "parquet", "motherduck", "snowflake",
    }

    def __init__(
        self,
        destination: str = "duckdb",
        dataset_name: str = "datawarehouse",
        pipeline_dir: Optional[Path] = None,
    ) -> None:
        if destination not in self.VALID_DESTINATIONS:
            raise ValueError(
                f"Unknown destination '{destination}'. "
                f"Valid: {sorted(self.VALID_DESTINATIONS)}"
            )

        self._destination = destination
        self._dataset_name = dataset_name
        self._pipeline_dir = str(pipeline_dir or Path("dlt_pipelines"))

        self._pipeline = dlt.pipeline(
            pipeline_name="datawarehouse_ingest",
            destination=destination,
            dataset_name=dataset_name,
            pipelines_dir=self._pipeline_dir,
        )
        logger.info("dlt pipeline initialized: %s → %s", destination, dataset_name)

    # ------------------------------------------------------------------
    # Loaders
    # ------------------------------------------------------------------

    def load_rest_api(
        self,
        url: str,
        table_name: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        paginator: str = "auto",
        write_disposition: str = "merge",
    ) -> Dict[str, Any]:
        """Load data from a REST API endpoint.

        Args:
            url: API endpoint URL.
            table_name: Target table name.
            params: Query parameters.
            headers: Custom HTTP headers.
            paginator: Pagination strategy (``"auto"``, ``"json_link"``,
                       ``"header_link"``, ``"offset"``, ``"page_number"``).
            write_disposition: ``"append"``, ``"replace"``, or ``"merge"``.

        Returns:
            dlt load info dict with ``rows_loaded``, ``schema``, etc.
        """
        # Build a dlt resource from the REST API
        @dlt.resource(
            name=table_name,
            write_disposition=write_disposition,
        )
        def _api_resource():
            import requests
            session = requests.Session()
            if headers:
                session.headers.update(headers)

            page = 1
            while True:
                p = dict(params or {})
                if paginator == "page_number":
                    p["page"] = page
                elif paginator == "offset":
                    p["offset"] = (page - 1) * (p.get("limit", 100))

                resp = session.get(url, params=p, timeout=30)
                resp.raise_for_status()
                data = resp.json()

                # Handle various response shapes
                if isinstance(data, list):
                    items = data
                elif "data" in data:
                    items = data["data"]
                elif "results" in data:
                    items = data["results"]
                elif "items" in data:
                    items = data["items"]
                else:
                    items = [data]

                if not items:
                    break

                yield from items
                page += 1

                # Safety limit
                if page > 100:
                    logger.warning("Pagination limit reached for %s", url)
                    break

        info = self._pipeline.run(_api_resource)
        logger.info("dlt loaded %s: %d rows → %s.%s",
                    url, info.loads_ids, self._dataset_name, table_name)
        return {
            "table": table_name,
            "dataset": self._dataset_name,
            "destination": self._destination,
            "load_info": str(info),
        }

    def load_csv_directory(
        self,
        dir_path: Path,
        write_disposition: str = "replace",
    ) -> int:
        """Load all CSV files from a directory as tables.

        Returns number of files loaded.
        """
        count = 0
        for csv_file in sorted(dir_path.glob("*.csv")):
            table_name = csv_file.stem

            @dlt.resource(
                name=table_name,
                write_disposition=write_disposition,
            )
            def _csv_resource(path=csv_file):
                import csv
                with open(path, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    yield from reader

            self._pipeline.run(_csv_resource)
            count += 1
            logger.debug("dlt loaded CSV: %s → %s", csv_file.name, table_name)

        return count

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def schema_info(self) -> Dict[str, Any]:
        """Return information about the current pipeline schema."""
        schema = self._pipeline.default_schema
        return {
            "name": schema.name,
            "tables": list(schema.tables.keys()),
            "version": schema.version,
            "dataset": self._dataset_name,
            "destination": self._destination,
        }

    def pipeline_stats(self) -> Dict[str, Any]:
        """Return pipeline run statistics."""
        return {
            "name": self._pipeline.pipeline_name,
            "dataset": self._dataset_name,
            "destination": self._destination,
            "loads_count": len(self._pipeline.list_load_packages()),
            "last_trace": str(self._pipeline.last_trace) if self._pipeline.last_trace else None,
        }
