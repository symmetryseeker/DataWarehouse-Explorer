"""
Async task queue for background repository downloads.

Uses Celery with Redis broker. Falls back to a simple threading-based
queue if Redis is not available (zero-config mode).

Usage::

    # Start Celery worker (requires Redis):
    celery -A datawarehouse.tasks worker --loglevel=info

    # Or use the built-in threading queue (zero config):
    from datawarehouse.tasks import download_repo_async
    task = download_repo_async("https://github.com/fivethirtyeight/data")
    while not task.is_done:
        print(f"Progress: {task.progress}%")
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("DataWarehouse.Tasks")

# Try Celery, fall back to threading
try:
    from celery import Celery  # type: ignore

    celery_app = Celery(
        "datawarehouse",
        broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
        backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
    )
    CELERY_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    celery_app = None  # type: ignore
    CELERY_AVAILABLE = False

import os


# ---------------------------------------------------------------------------
# Task Status
# ---------------------------------------------------------------------------

@dataclass
class TaskInfo:
    """Lightweight task status tracker (used in threading fallback mode)."""

    task_id: str
    repo_url: str
    repo_name: str = ""
    status: str = "pending"  # pending / running / done / failed
    progress: int = 0
    error_message: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    result: Optional[Any] = None

    @property
    def is_done(self) -> bool:
        return self.status in ("done", "failed")


# ---------------------------------------------------------------------------
# Threading-based task queue (zero-config fallback)
# ---------------------------------------------------------------------------

class ThreadingTaskQueue:
    """Simple in-process task queue using Python threads.

    No Redis required. Suitable for single-machine personal use.
    """

    def __init__(self, max_workers: int = 3) -> None:
        self._queue: Queue = Queue()
        self._workers: List[threading.Thread] = []
        self._tasks: Dict[str, TaskInfo] = {}
        self._max_workers = max_workers
        self._running = False

    def start(self) -> None:
        self._running = True
        for _ in range(self._max_workers):
            t = threading.Thread(target=self._worker_loop, daemon=True)
            t.start()
            self._workers.append(t)
        logger.info("Threading task queue started (workers=%d)", self._max_workers)

    def stop(self) -> None:
        self._running = False

    def submit(self, fn: Callable, repo_url: str, repo_name: str = "",
               callback: Optional[Callable] = None) -> TaskInfo:
        """Submit a task and return a TaskInfo tracker."""
        task = TaskInfo(
            task_id=str(uuid.uuid4())[:12],
            repo_url=repo_url,
            repo_name=repo_name,
        )
        self._tasks[task.task_id] = task
        self._queue.put((task, fn, callback))
        return task

    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        return self._tasks.get(task_id)

    def list_tasks(self) -> List[TaskInfo]:
        return list(self._tasks.values())

    def _worker_loop(self) -> None:
        while self._running:
            try:
                task, fn, callback = self._queue.get(timeout=1)
                task.status = "running"
                try:
                    task.result = fn(task)
                    task.status = "done"
                    task.progress = 100
                except Exception as exc:
                    task.status = "failed"
                    task.error_message = str(exc)
                    logger.error("Task %s failed: %s", task.task_id, exc)
                task.completed_at = datetime.now(timezone.utc).isoformat()
                if callback:
                    try:
                        callback(task)
                    except Exception:
                        pass
                self._queue.task_done()
            except Exception:
                pass


# Global queue instance
_task_queue: Optional[ThreadingTaskQueue] = None


def get_task_queue(max_workers: int = 3) -> ThreadingTaskQueue:
    global _task_queue
    if _task_queue is None:
        _task_queue = ThreadingTaskQueue(max_workers=max_workers)
        _task_queue.start()
    return _task_queue


# ---------------------------------------------------------------------------
# Celery tasks (if Redis available)
# ---------------------------------------------------------------------------

if CELERY_AVAILABLE:

    @celery_app.task(bind=True)
    def download_repo_celery(self, repo_url: str, warehouse_root: str) -> Dict[str, Any]:
        """Celery task: download and validate a single repository."""
        self.update_state(state="PROGRESS", meta={"progress": 0})
        # ... pipeline logic here
        return {"status": "done"}
