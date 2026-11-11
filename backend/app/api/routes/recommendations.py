import logging
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from pymongo.errors import PyMongoError

from backend.app.core.config import MongoConfigurationError
from backend.app.db.mongo import get_database
from backend.app.recommendations.engine import STRATEGIES
from backend.app.recommendations.service import RecommendationService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])

_cached_database: Any | None = None
_cached_service: RecommendationService | None = None


class GenerateRecommendationRequest(BaseModel):
    strategy: Literal["popularity", "content", "hybrid"] = "hybrid"
    k: int = Field(default=10, ge=1, le=100)
    as_of_time: datetime | None = None
    session_id: str | None = None
    generation_run_id: str | None = None

    @field_validator("as_of_time")
    @classmethod
    def as_of_must_be_timezone_aware(
        cls, value: datetime | None
    ) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("as_of_time must include a timezone.")
        return value


class EvaluationRequest(BaseModel):
    k_values: list[int] = Field(default_factory=lambda: [5, 10], min_length=1)
    generation_run_id: str | None = None

    @field_validator("k_values")
    @classmethod
    def evaluation_ks_must_be_positive(cls, values: list[int]) -> list[int]:
        if any(value < 1 or value > 100 for value in values):
            raise ValueError("Each K must be between 1 and 100.")
        return sorted(set(values))


def get_recommendation_service() -> RecommendationService:
    global _cached_database, _cached_service
    try:
        database = get_database()
    except MongoConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if _cached_service is None or _cached_database is not database:
        _cached_database = database
        _cached_service = RecommendationService(database)
    return _cached_service


@router.post("/customers/{customer_id}")
def generate_recommendations(
    customer_id: str,
    request: GenerateRecommendationRequest = Body(...),
    service: RecommendationService = Depends(get_recommendation_service),
) -> dict[str, Any]:
    try:
        return service.generate_for_customer(
            customer_id,
            strategy=request.strategy,
            k=request.k,
            as_of_time=request.as_of_time,
            session_id=request.session_id,
            generation_run_id=request.generation_run_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PyMongoError as exc:
        logger.exception("Recommendation generation failed during MongoDB access")
        raise HTTPException(
            status_code=503, detail="Recommendation data is unavailable in MongoDB."
        ) from exc


@router.get("/customers/{customer_id}")
def get_customer_recommendations(
    customer_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    service: RecommendationService = Depends(get_recommendation_service),
) -> list[dict[str, Any]]:
    try:
        return service.list_customer_recommendations(customer_id, limit=limit)
    except PyMongoError as exc:
        logger.exception("Recommendation retrieval failed during MongoDB access")
        raise HTTPException(
            status_code=503, detail="Recommendation data is unavailable in MongoDB."
        ) from exc


@router.post("/evaluations")
def run_recommendation_evaluation(
    request: EvaluationRequest = Body(default=EvaluationRequest()),
    service: RecommendationService = Depends(get_recommendation_service),
) -> list[dict[str, Any]]:
    try:
        return service.run_evaluation(
            k_values=request.k_values,
            generation_run_id=request.generation_run_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PyMongoError as exc:
        logger.exception("Recommendation evaluation failed during MongoDB access")
        raise HTTPException(
            status_code=503, detail="Evaluation data is unavailable in MongoDB."
        ) from exc


@router.get("/evaluations")
def get_recommendation_evaluations(
    model_run_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    service: RecommendationService = Depends(get_recommendation_service),
) -> list[dict[str, Any]]:
    try:
        return service.list_evaluation_results(
            model_run_id=model_run_id,
            limit=limit,
        )
    except PyMongoError as exc:
        logger.exception("Evaluation retrieval failed during MongoDB access")
        raise HTTPException(
            status_code=503, detail="Evaluation data is unavailable in MongoDB."
        ) from exc


@router.get("/strategies")
def get_recommendation_strategies() -> dict[str, Any]:
    information = RecommendationService.strategy_information()
    information["available_strategies"] = list(STRATEGIES)
    return information
