import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from pymongo.errors import DuplicateKeyError, PyMongoError
from bson.int64 import Int64

from backend.app.api.operations import operation_registry
from backend.app.api.routes.dashboard import get_dashboard_database
from backend.app.core.config import MongoConfigurationError
from backend.app.db.initialize import initialize_database
from backend.app.db.schema import CORE_COLLECTIONS
from backend.app.generator.anomalies import AnomalyConfig
from backend.app.generator.config import GENERATION_SEED, GenerationConfig
from backend.app.generator.engine import GenerationEngine
from backend.app.generator.ids import dataset_id, dataset_fingerprint
from backend.app.generator.targets import (
    CompositeGenerationTarget,
    ExportGenerationTarget,
    MongoGenerationTarget,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/generation", tags=["generation"])
GENERATION_LOCK_ID = "API_GENERATION_LOCK"
GENERATION_LOCK_LEASE = timedelta(minutes=15)


class GenerationRequest(BaseModel):
    scale: Literal["starter", "full"] = "starter"
    seed: int = GENERATION_SEED
    batch_size: int = Field(default=1_000, ge=1, le=10_000)
    inject_anomalies: bool = False

    @field_validator("seed")
    @classmethod
    def seed_is_fixed(cls, value: int) -> int:
        if value != GENERATION_SEED:
            raise ValueError(f"seed is fixed at {GENERATION_SEED}.")
        return value


class TrackedGenerationTarget:
    def __init__(
        self,
        target: CompositeGenerationTarget,
        job_id: str,
        database: Any,
    ) -> None:
        self.target = target
        self.job_id = job_id
        self.database = database

    def write_batch(
        self, collection_name: str, documents: list[dict[str, Any]]
    ) -> None:
        self.target.write_batch(collection_name, documents)
        now = datetime.now(timezone.utc)
        self.database["generation_runs"].update_one(
            {"_id": GENERATION_LOCK_ID, "lock_token": self.job_id},
            {"$set": {"expires_at": now + GENERATION_LOCK_LEASE}},
        )
        job = operation_registry.get(self.job_id) or {}
        operation_registry.update(
            self.job_id,
            status="running",
            current_collection=collection_name,
            records_processed=job.get("records_processed", 0) + len(documents),
        )

    def finalize(self, manifest: dict[str, Any]) -> None:
        self.target.finalize(manifest)

    def close(self) -> None:
        self.target.close()


def _acquire_generation_lock(database: Any, seed: int, job_id: str) -> None:
    now = datetime.now(timezone.utc)
    database["generation_runs"].find_one_and_update(
        {
            "_id": GENERATION_LOCK_ID,
            "$or": [
                {"expires_at": {"$lte": now}},
                {"expires_at": {"$exists": False}},
            ],
        },
        {
            "$set": {
                "status": "running",
                "started_at": now,
                "completed_at": None,
                "expires_at": now + GENERATION_LOCK_LEASE,
                "lock_token": job_id,
            },
            "$setOnInsert": {
                "seed": Int64(seed),
                "configuration": {"operation_lock": True},
                "collection_counts": {},
                "checksums": {},
                "error": None,
            },
        },
        upsert=True,
    )


def _release_generation_lock(database: Any, job_id: str) -> None:
    database["generation_runs"].delete_one(
        {"_id": GENERATION_LOCK_ID, "lock_token": job_id}
    )


def _config_for(scale: str) -> GenerationConfig:
    return GenerationConfig.starter() if scale == "starter" else GenerationConfig.full()


def _run_generation(
    database: Any,
    job_id: str,
    config: GenerationConfig,
    batch_size: int,
    inject_anomalies: bool,
) -> None:
    try:
        operation_registry.update(job_id, status="running")
        initialize_database(database)
        run_id = dataset_id(
            "generation_runs",
            dataset_fingerprint(config.as_dict()),
            "",
        )
        existing_run = database["generation_runs"].find_one({"_id": run_id})
        if existing_run:
            raise RuntimeError(
                "This deterministic generation run already exists in MongoDB."
            )
        composite = CompositeGenerationTarget(
            MongoGenerationTarget(database),
            ExportGenerationTarget(Path("generated-data")),
        )
        target = TrackedGenerationTarget(composite, job_id, database)
        manifest = GenerationEngine(
            config,
            batch_size=batch_size,
            anomaly_config=AnomalyConfig(enabled=inject_anomalies),
        ).run(target)
        try:
            _release_generation_lock(database, job_id)
        except PyMongoError:
            logger.exception("Could not release the completed generation lease")
        operation_registry.finish(
            job_id,
            status="completed",
            result=manifest.as_dict(),
        )
    except Exception:
        logger.exception("API-triggered synthetic data generation failed")
        try:
            _release_generation_lock(database, job_id)
        except PyMongoError:
            logger.exception("Could not release the failed generation lease")
        operation_registry.finish(
            job_id,
            status="failed",
            error=(
                "Generation failed. Check the backend logs and MongoDB state; "
                "partial writes, if any, are not automatically deleted."
            ),
        )


@router.post("", status_code=202)
def start_generation(
    request: GenerationRequest,
    background_tasks: BackgroundTasks,
    database: Any = Depends(get_dashboard_database),
) -> dict[str, Any]:
    config = _config_for(request.scale)
    try:
        database.command("ping")
        run_id = dataset_id(
            "generation_runs",
            dataset_fingerprint(config.as_dict()),
            "",
        )
        if database["generation_runs"].find_one({"_id": run_id}):
            raise HTTPException(
                status_code=409,
                detail="This deterministic dataset run already exists; generation will not overwrite it.",
            )
        guarded_collections = (*CORE_COLLECTIONS, "dataset_splits", "ground_truth_labels", "anomaly_fixtures")
        guarded_collections = (
            *CORE_COLLECTIONS,
            "dataset_splits",
            "ground_truth_labels",
            "anomaly_fixtures",
        )
        for collection_name in guarded_collections:
            if database[collection_name].find_one({}, {"_id": 1}):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Collection '{collection_name}' already contains data. "
                        "Generation is append-only and will not overwrite existing records."
                    ),
                )
        job = operation_registry.start(
            "generation",
            {
                "scale": request.scale,
                "seed": request.seed,
                "batch_size": request.batch_size,
                "inject_anomalies": request.inject_anomalies,
            },
        )
        try:
            _acquire_generation_lock(database, request.seed, job["_id"])
        except DuplicateKeyError as exc:
            operation_registry.finish(
                job["_id"],
                status="failed",
                error="Another API worker is already generating a dataset.",
            )
            raise HTTPException(
                status_code=409,
                detail="Another API worker is already generating a dataset.",
            ) from exc
        except PyMongoError as exc:
            operation_registry.finish(
                job["_id"],
                status="failed",
                error="Could not reserve the generation operation in MongoDB.",
            )
            logger.exception("Could not reserve a MongoDB generation lease")
            raise HTTPException(
                status_code=503,
                detail="Could not reserve the generation operation in MongoDB.",
            ) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MongoConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PyMongoError as exc:
        logger.exception("Cannot start generation because MongoDB is unavailable")
        raise HTTPException(
            status_code=503,
            detail="Generation could not start because MongoDB is unavailable.",
        ) from exc
    background_tasks.add_task(
        _run_generation,
        database,
        job["_id"],
        config,
        request.batch_size,
        request.inject_anomalies,
    )
    return job


@router.get("/jobs/{job_id}")
def get_generation_job(job_id: str) -> dict[str, Any]:
    job = operation_registry.get(job_id, operation="generation")
    if job is None:
        raise HTTPException(status_code=404, detail="Generation job was not found.")
    return job


@router.get("/configurations")
def get_generation_configurations() -> dict[str, Any]:
    return {
        "seed": GENERATION_SEED,
        "default_batch_size": 1_000,
        "scales": [
            {
                "value": "starter",
                "label": "Starter",
                "configuration": GenerationConfig.starter().as_dict(),
            },
            {
                "value": "full",
                "label": "Full",
                "configuration": GenerationConfig.full().as_dict(),
            },
        ],
    }


@router.get("/status")
def get_generation_status() -> dict[str, Any]:
    return operation_registry.latest("generation") or {
        "status": "not_started",
        "detail": "No generation job has been started in this API process.",
    }
