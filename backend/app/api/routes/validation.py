import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from pymongo.errors import PyMongoError

from backend.app.api.operations import operation_registry
from backend.app.api.routes.dashboard import get_dashboard_database
from backend.app.db.initialize import initialize_database
from backend.app.db.schema import COLLECTION_NAMES, CORE_COLLECTIONS
from backend.app.validation.engine import ValidationEngine
from backend.app.validation.targets import (
    CompositeValidationTarget,
    ValidationExportTarget,
    ValidationMongoTarget,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/validation", tags=["validation"])


class ValidationRequest(BaseModel):
    generation_run_id: str | None = None
    batch_size: int = 1_000


class TrackedValidationTarget:
    def __init__(self, target: CompositeValidationTarget, job_id: str) -> None:
        self.target = target
        self.job_id = job_id
        self.issue_count = 0

    def write_batch(self, documents: list[dict[str, Any]]) -> None:
        self.target.write_batch(documents)
        self.issue_count += len(documents)
        operation_registry.update(
            self.job_id,
            status="running",
            issues_written=self.issue_count,
        )

    def finalize(self, report: dict[str, Any]) -> None:
        self.target.finalize(report)

    def close(self) -> None:
        self.target.close()


def _run_validation(
    database: Any,
    job_id: str,
    generation_run_id: str,
    batch_size: int,
) -> None:
    try:
        operation_registry.update(job_id, status="running")
        initialize_database(database)
        sources = {
            name: (lambda collection=name: database[collection].find({}))
            for name in COLLECTION_NAMES
            if name != "validation_issues"
        }
        target = TrackedValidationTarget(
            CompositeValidationTarget(
                ValidationMongoTarget(database),
                ValidationExportTarget(
                    Path("validation-output") / generation_run_id
                ),
            ),
            job_id,
        )
        report = ValidationEngine(batch_size=batch_size).run(
            sources,
            generation_run_id=generation_run_id,
            target=target,
        )
        report_data = report.as_dict()
        database["generation_runs"].update_one(
            {"_id": generation_run_id},
            {"$set": {"validation_summary": report_data}},
        )
        operation_registry.finish(
            job_id,
            status="completed",
            result=report_data,
        )
    except Exception:
        logger.exception("API-triggered dataset validation failed")
        operation_registry.finish(
            job_id,
            status="failed",
            error="Validation failed. Check the backend logs and MongoDB state.",
        )


@router.post("", status_code=202)
def start_validation(
    request: ValidationRequest,
    background_tasks: BackgroundTasks,
    database: Any = Depends(get_dashboard_database),
) -> dict[str, Any]:
    if request.batch_size < 1 or request.batch_size > 10_000:
        raise HTTPException(status_code=422, detail="batch_size must be between 1 and 10000.")
    try:
        database.command("ping")
        generation_run = (
            database["generation_runs"].find_one(
                {"_id": request.generation_run_id, "status": "completed"}
            )
            if request.generation_run_id
            else database["generation_runs"].find_one(
                {"status": "completed"},
                sort=[("completed_at", -1), ("_id", 1)],
            )
        )
        if generation_run is None:
            raise HTTPException(
                status_code=404,
                detail="No matching completed generation run was found.",
            )
        job = operation_registry.start(
            "validation",
            {
                "generation_run_id": generation_run["_id"],
                "batch_size": request.batch_size,
            },
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PyMongoError as exc:
        logger.exception("Cannot start validation because MongoDB is unavailable")
        raise HTTPException(
            status_code=503,
            detail="Validation could not start because MongoDB is unavailable.",
        ) from exc
    background_tasks.add_task(
        _run_validation,
        database,
        job["_id"],
        generation_run["_id"],
        request.batch_size,
    )
    return job


@router.get("/jobs/{job_id}")
def get_validation_job(job_id: str) -> dict[str, Any]:
    job = operation_registry.get(job_id, operation="validation")
    if job is None:
        raise HTTPException(status_code=404, detail="Validation job was not found.")
    return job


@router.get("/summary")
def get_validation_summary(
    generation_run_id: str | None = None,
    database: Any = Depends(get_dashboard_database),
) -> dict[str, Any]:
    try:
        generation_run = (
            database["generation_runs"].find_one({"_id": generation_run_id})
            if generation_run_id
            else database["generation_runs"].find_one(
                {"status": "completed"},
                sort=[("completed_at", -1), ("_id", 1)],
            )
        )
        if generation_run is None:
            return {
                "status": "not_available",
                "issue_count": None,
                "detail": "No completed generation run is available.",
            }
        job = operation_registry.latest("validation")
        if (
            job
            and job.get("status") == "completed"
            and job.get("result", {}).get("generation_run_id") == generation_run["_id"]
        ):
            return {"status": "completed", **job["result"]}
        return _summary_for_database(database, generation_run)
    except PyMongoError as exc:
        logger.exception("Validation summary could not be read")
        raise HTTPException(
            status_code=503, detail="Validation data is unavailable in MongoDB."
        ) from exc


def _summary_for_database(database: Any, generation_run: dict[str, Any]) -> dict[str, Any]:
    run_id = generation_run["_id"]
    stored_summary = generation_run.get("validation_summary")
    if isinstance(stored_summary, dict):
        return {"status": "completed", **stored_summary}
    issues = database["validation_issues"]
    summary_path = (
        Path("validation-output") / run_id / "validation_summary.json"
    )
    if not summary_path.is_file():
        summary_path = Path("validation-output") / "validation_summary.json"
    if summary_path.is_file():
        try:
            with summary_path.open(encoding="utf-8") as file:
                summary = json.load(file)
            if summary.get("generation_run_id") == run_id:
                return {"status": "completed", **summary}
        except (OSError, ValueError):
            logger.exception("Could not read validation summary export")

    issue_count = issues.count_documents({"generation_run_id": run_id})
    type_counts: dict[str, int] = {}
    severity_counts: dict[str, int] = {}
    if issue_count:
        for row in issues.aggregate(
            [
                {"$match": {"generation_run_id": run_id}},
                {
                    "$group": {
                        "_id": {
                            "severity": "$severity",
                            "issue_type": "$issue_type",
                        },
                        "count": {"$sum": 1},
                    }
                },
            ]
        ):
            severity = row["_id"]["severity"]
            issue_type = row["_id"]["issue_type"]
            severity_counts[severity] = severity_counts.get(severity, 0) + row["count"]
            type_counts[issue_type] = type_counts.get(issue_type, 0) + row["count"]
        return {
            "status": "completed",
            "generation_run_id": run_id,
            "issue_count": issue_count,
            "counts_by_issue_type": type_counts,
            "counts_by_severity": severity_counts,
            "clean_record_count": sum(
                generation_run.get("collection_counts", {}).get(name, 0)
                for name in CORE_COLLECTIONS
            ),
            "anomalous_record_count": database["anomaly_fixtures"].count_documents(
                {"generation_run_id": run_id}
            ),
            "detail": "Summary reconstructed from persisted validation issues.",
        }
    return {
        "status": "not_run",
        "generation_run_id": run_id,
        "issue_count": None,
        "counts_by_issue_type": {},
        "counts_by_severity": {},
        "clean_record_count": None,
        "anomalous_record_count": None,
        "detail": "No validation summary was found for this dataset.",
    }


@router.get("/issues")
def list_validation_issues(
    generation_run_id: str | None = None,
    severity: str | None = Query(default=None, max_length=20),
    issue_type: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    database: Any = Depends(get_dashboard_database),
) -> dict[str, Any]:
    query: dict[str, Any] = {}
    if generation_run_id:
        query["generation_run_id"] = generation_run_id
    if severity:
        query["severity"] = severity
    if issue_type:
        query["issue_type"] = issue_type
    try:
        collection = database["validation_issues"]
        total = collection.count_documents(query)
        issues = list(
            collection.find(query)
            .sort([("detected_at", -1), ("issue_id", 1)])
            .skip(offset)
            .limit(limit)
        )
        return {"items": issues, "total": total, "limit": limit, "offset": offset}
    except PyMongoError as exc:
        logger.exception("Validation issues could not be read")
        raise HTTPException(
            status_code=503, detail="Validation issues are unavailable in MongoDB."
        ) from exc


@router.get("/status")
def get_validation_status() -> dict[str, Any]:
    return operation_registry.latest("validation") or {
        "status": "not_started",
        "detail": "No validation job has been started in this API process.",
    }
