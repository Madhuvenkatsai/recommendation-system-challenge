from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.config import cors_allowed_origins
from backend.app.api.routes.catalog import router as catalog_router
from backend.app.api.routes.dashboard import router as dashboard_router
from backend.app.api.routes.generation import router as generation_router
from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.recommendations import router as recommendations_router
from backend.app.api.routes.validation import router as validation_router
from backend.app.db.mongo import close_mongo_connection


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    close_mongo_connection()


app = FastAPI(
    title="E-commerce Product Recommendation System",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(cors_allowed_origins()),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)
app.include_router(health_router)
app.include_router(dashboard_router)
app.include_router(catalog_router)
app.include_router(generation_router)
app.include_router(validation_router)
app.include_router(recommendations_router)
