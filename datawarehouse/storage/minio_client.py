"""
MinIO / S3-compatible object storage client.

Provides an S3-like interface for storing and retrieving data files.
MinIO is a self-hosted S3-compatible object store — no cloud bills.

Usage::

    from datawarehouse.storage import MinIOClient

    client = MinIOClient(endpoint="localhost:9000",
                         access_key="minioadmin",
                         secret_key="minioadmin")
    client.upload("E:/DataWarehouse/data/file.csv", "raw-bucket/file.csv")
    client.download("raw-bucket/file.csv", "/tmp/file.csv")
"""

from __future__ import annotations

import logging
import sys
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from minio import Minio  # type: ignore
    from minio.error import S3Error  # type: ignore
except ImportError:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "minio", "--quiet"]
    )
    from minio import Minio  # type: ignore
    from minio.error import S3Error  # type: ignore

logger = logging.getLogger("DataWarehouse.Storage")


class MinIOClient:
    """S3-compatible object storage client backed by MinIO.

    Args:
        endpoint: MinIO server address (e.g., ``"localhost:9000"``).
        access_key: MinIO access key.
        secret_key: MinIO secret key.
        secure: Use HTTPS (default: False for local MinIO).
    """

    # Default buckets created on connect
    DEFAULT_BUCKETS = ["raw-data", "processed-data", "models", "metadata"]

    def __init__(
        self,
        endpoint: str = "localhost:9000",
        access_key: str = "minioadmin",
        secret_key: str = "minioadmin",
        secure: bool = False,
    ) -> None:
        self._client = Minio(
            endpoint, access_key=access_key,
            secret_key=secret_key, secure=secure,
        )
        self._endpoint = endpoint
        self._ensure_buckets()
        logger.info("MinIO client connected to %s", endpoint)

    # ------------------------------------------------------------------
    # Bucket management
    # ------------------------------------------------------------------

    def _ensure_buckets(self) -> None:
        """Create default buckets if they don't exist."""
        existing = {b.name for b in self._client.list_buckets()}
        for bucket in self.DEFAULT_BUCKETS:
            if bucket not in existing:
                self._client.make_bucket(bucket)
                logger.info("Created bucket: %s", bucket)

    def list_buckets(self) -> List[str]:
        return [b.name for b in self._client.list_buckets()]

    # ------------------------------------------------------------------
    # Upload / Download
    # ------------------------------------------------------------------

    def upload(self, local_path: Path, object_path: str,
               bucket: str = "raw-data") -> str:
        """Upload a local file to object storage.

        Args:
            local_path: Path to the local file.
            object_path: Object key in the bucket (e.g., ``"csv/weather.csv"``).
            bucket: Target bucket name.

        Returns:
            The S3 URI (``s3://bucket/object_path``).
        """
        if not local_path.exists():
            raise FileNotFoundError(f"File not found: {local_path}")

        self._client.fput_object(
            bucket, object_path, str(local_path),
        )
        s3_uri = f"s3://{bucket}/{object_path}"
        logger.info("Uploaded %s → %s (%s)", local_path.name, s3_uri,
                     self._human_size(local_path.stat().st_size))
        return s3_uri

    def download(self, object_path: str, local_path: Path,
                 bucket: str = "raw-data") -> Path:
        """Download an object from storage to a local file."""
        self._client.fget_object(bucket, object_path, str(local_path))
        logger.info("Downloaded s3://%s/%s → %s", bucket, object_path, local_path)
        return local_path

    def upload_directory(self, dir_path: Path, prefix: str = "",
                         bucket: str = "raw-data") -> int:
        """Recursively upload all files in a directory.

        Returns number of files uploaded.
        """
        count = 0
        for f in dir_path.rglob("*"):
            if f.is_file():
                rel = str(f.relative_to(dir_path)).replace("\\", "/")
                obj_path = f"{prefix}/{rel}" if prefix else rel
                self.upload(f, obj_path, bucket)
                count += 1
        return count

    # ------------------------------------------------------------------
    # List / Search
    # ------------------------------------------------------------------

    def list_objects(self, prefix: str = "",
                     bucket: str = "raw-data") -> List[Dict[str, Any]]:
        """List objects in a bucket, optionally filtered by prefix."""
        objects = self._client.list_objects(bucket, prefix=prefix, recursive=True)
        return [
            {
                "name": obj.object_name,
                "size": obj.size,
                "size_human": self._human_size(obj.size),
                "last_modified": str(obj.last_modified),
                "s3_uri": f"s3://{bucket}/{obj.object_name}",
            }
            for obj in objects
        ]

    def object_exists(self, object_path: str, bucket: str = "raw-data") -> bool:
        """Check if an object exists."""
        try:
            self._client.stat_object(bucket, object_path)
            return True
        except S3Error:
            return False

    # ------------------------------------------------------------------
    # Data Warehouse integration
    # ------------------------------------------------------------------

    def store_warehouse_data(self, warehouse_root: Path) -> int:
        """Upload all structured data from the warehouse to MinIO.

        Maps the warehouse directory structure to S3 buckets:
        - ``data/structured/csv/`` → ``raw-data/csv/``
        - ``data/structured/json/`` → ``raw-data/json/``
        - ``code/`` → ``raw-data/code/``

        Returns total files uploaded.
        """
        count = 0
        data_dir = warehouse_root / "data" / "structured"
        if data_dir.is_dir():
            count += self.upload_directory(data_dir, prefix="structured", bucket="raw-data")

        code_dir = warehouse_root / "code"
        if code_dir.is_dir():
            count += self.upload_directory(code_dir, prefix="code", bucket="raw-data")

        logger.info("Warehouse sync complete: %d files → MinIO", count)
        return count

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _human_size(size: int) -> str:
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if abs(size) < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
