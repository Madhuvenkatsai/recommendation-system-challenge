import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pymongo.errors import PyMongoError

from backend.app.api.operations import operation_registry
from backend.app.core.config import MongoConfigurationError
from backend.app.db.mongo import get_database
from backend.app.db.schema import CORE_COLLECTIONS
from backend.app.recommendations.service import RecommendationService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


def get_dashboard_database() -> Any:
    try:
        return get_database()
    except MongoConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _latest_generation(database: Any) -> dict[str, Any] | None:
    return database["generation_runs"].find_one(
        {"status": "completed"},
        sort=[("completed_at", -1), ("_id", 1)],
        projection={
            "_id": 1,
            "seed": 1,
            "configuration": 1,
            "status": 1,
            "started_at": 1,
            "completed_at": 1,
            "collection_counts": 1,
            "checksums": 1,
            "validation_summary": 1,
        },
    )


def _validation_summary(
    database: Any, generation_run: dict[str, Any] | None
) -> dict[str, Any]:
    if generation_run is None:
        return {
            "status": "not_available",
            "generation_run_id": None,
            "issue_count": None,
            "counts_by_severity": {},
            "counts_by_issue_type": {},
            "clean_record_count": None,
            "anomalous_record_count": None,
            "detail": "Generate a dataset before running validation.",
        }

    run_id = generation_run["_id"]
    stored_summary = generation_run.get("validation_summary")
    if isinstance(stored_summary, dict):
        return {"status": "completed", **stored_summary}
    summary_path = (
        Path("validation-output") / run_id / "validation_summary.json"
    )
    if not summary_path.is_file():
        summary_path = Path("validation-output") / "validation_summary.json"
    if summary_path.is_file():
        try:
            with summary_path.open(encoding="utf-8") as file:
                saved = json.load(file)
        except (OSError, json.JSONDecodeError):
            logger.exception("Could not read the validation summary export")
            saved = None
        if saved and saved.get("generation_run_id") == run_id:
            return {"status": "completed", **saved}

    issues = database["validation_issues"]
    issue_count = issues.count_documents({"generation_run_id": run_id})
    if issue_count:
        by_severity: dict[str, int] = {}
        by_type: dict[str, int] = {}
        for row in issues.aggregate(
            [
                {"$match": {"generation_run_id": run_id}},
                {
                    "$group": {
                        "_id": {"severity": "$severity", "issue_type": "$issue_type"},
                        "count": {"$sum": 1},
                    }
                },
            ]
        ):
            by_severity[row["_id"]["severity"]] = (
                by_severity.get(row["_id"]["severity"], 0) + row["count"]
            )
            by_type[row["_id"]["issue_type"]] = (
                by_type.get(row["_id"]["issue_type"], 0) + row["count"]
            )
        return {
            "status": "completed",
            "generation_run_id": run_id,
            "issue_count": issue_count,
            "counts_by_severity": by_severity,
            "counts_by_issue_type": by_type,
            "clean_record_count": sum(
                generation_run.get("collection_counts", {}).get(name, 0)
                for name in CORE_COLLECTIONS
            ),
            "anomalous_record_count": database["anomaly_fixtures"].count_documents(
                {"generation_run_id": run_id}
            ),
            "detail": "Summary reconstructed from persisted validation issues.",
        }
    latest_job = operation_registry.latest("validation")
    if (
        latest_job
        and latest_job.get("status") == "completed"
        and latest_job.get("result", {}).get("generation_run_id") == run_id
    ):
        return {"status": "completed", **latest_job["result"]}
    return {
        "status": "not_run",
        "generation_run_id": run_id,
        "issue_count": None,
        "counts_by_severity": {},
        "counts_by_issue_type": {},
        "clean_record_count": None,
        "anomalous_record_count": None,
        "detail": "No validation summary was found for this dataset.",
    }


@router.get("/overview")
def get_dashboard_overview(
    database: Any = Depends(get_dashboard_database),
) -> dict[str, Any]:
    try:
        database.command("ping")
        generation_run = _latest_generation(database)
        counts = {
            collection: database[collection].count_documents({})
            for collection in ("customers", "products", "sessions", "orders")
        }
        latest_evaluations = list(
            database["evaluation_results"]
            .find({})
            .sort([("evaluated_at", -1), ("_id", 1)])
            .limit(12)
        )
        model_ids = sorted(
            {result["model_run_id"] for result in latest_evaluations if result.get("model_run_id")}
        )
        model_runs = {
            model["_id"]: model
            for model in database["model_runs"].find(
                {"_id": {"$in": model_ids}},
                {"_id": 1, "algorithm": 1, "model_version": 1},
            )
        }
        for result in latest_evaluations:
            model = model_runs.get(result.get("model_run_id"), {})
            result["strategy"] = model.get("algorithm")
            result["model_version"] = model.get("model_version")
        return {
            "database": {
                "status": "connected",
                "engine": "mongodb",
                "name": database.name,
            },
            "counts": counts,
            "generation": {
                "status": (
                    generation_run["status"] if generation_run else "not_generated"
                ),
                "latest_run": generation_run,
                "active_job": operation_registry.latest("generation"),
            },
            "validation": _validation_summary(database, generation_run),
            "recommendations": RecommendationService.strategy_information(),
            "latest_evaluations": latest_evaluations,
        }
    except PyMongoError as exc:
        logger.exception("Dashboard overview could not read MongoDB data")
        raise HTTPException(
            status_code=503,
            detail="Dashboard data is unavailable; verify the MongoDB connection.",
        ) from exc
