from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4
from typing import Any


class OperationRegistry:
    """Tracks API-triggered long-running work for this application process."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._active_job_id: str | None = None

    def start(self, operation: str, configuration: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self._active_job_id is not None:
                active = self._jobs[self._active_job_id]
                raise RuntimeError(
                    f"{active['operation']} operation {active['_id']} is already running."
                )
            job_id = f"JOB{uuid4().hex.upper()}"
            job = {
                "_id": job_id,
                "operation": operation,
                "status": "queued",
                "configuration": configuration,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "records_processed": 0,
            }
            self._jobs[job_id] = job
            self._active_job_id = job_id
            return dict(job)

    def get(self, job_id: str, *, operation: str | None = None) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or (operation and job["operation"] != operation):
                return None
            return dict(job)

    def latest(self, operation: str) -> dict[str, Any] | None:
        with self._lock:
            jobs = [
                job for job in self._jobs.values()
                if job["operation"] == operation
            ]
            if not jobs:
                return None
            return dict(max(jobs, key=lambda job: job["created_at"]))

    def update(self, job_id: str, **updates: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.update(updates)
            job["updated_at"] = datetime.now(timezone.utc)

    def finish(
        self,
        job_id: str,
        *,
        status: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.update(
                status=status,
                result=result,
                error=error,
                completed_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            if self._active_job_id == job_id:
                self._active_job_id = None


operation_registry = OperationRegistry()
