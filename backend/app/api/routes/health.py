import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from backend.app.core.config import MongoConfigurationError
from backend.app.repositories.health import check_database

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health", tags=["health"])
def liveness_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/v1/health", tags=["health"])
def database_health_check() -> JSONResponse:
    try:
        check_database()
    except MongoConfigurationError as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "not_configured", "detail": str(exc)},
        )
    except PyMongoError:
        logger.exception("MongoDB health check failed")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "detail": "MongoDB ping failed; verify the configured URI and server availability.",
            },
        )

    return JSONResponse(
        status_code=200,
        content={"status": "ok", "database": "mongodb"},
    )
