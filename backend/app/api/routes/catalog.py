import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.errors import PyMongoError

from backend.app.core.config import MongoConfigurationError
from backend.app.db.mongo import get_database

router = APIRouter(prefix="/api/v1", tags=["catalog"])


def get_catalog_database() -> Any:
    try:
        return get_database()
    except MongoConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/catalog/categories")
def list_categories(
    database: Any = Depends(get_catalog_database),
) -> list[dict[str, Any]]:
    try:
        return list(
            database["categories"].find(
                {},
                {
                    "_id": 1,
                    "name": 1,
                    "slug": 1,
                    "parent_category_id": 1,
                    "seasonal_tags": 1,
                    "active_from": 1,
                    "active_to": 1,
                },
            ).sort([("name", 1), ("_id", 1)])
        )
    except PyMongoError as exc:
        raise HTTPException(
            status_code=503, detail="Category data is unavailable in MongoDB."
        ) from exc


@router.get("/catalog/products")
def list_products(
    search: str | None = Query(default=None, max_length=100),
    category_id: str | None = Query(default=None, max_length=100),
    status: Literal["active", "unavailable", "discontinued"] | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    database: Any = Depends(get_catalog_database),
) -> dict[str, Any]:
    query: dict[str, Any] = {}
    if category_id:
        query["category_id"] = category_id
    if status:
        query["status"] = status
    if search and search.strip():
        pattern = re.escape(search.strip())
        query["$or"] = [
            {"_id": {"$regex": pattern, "$options": "i"}},
            {"name": {"$regex": pattern, "$options": "i"}},
            {"brand": {"$regex": pattern, "$options": "i"}},
        ]
    try:
        collection = database["products"]
        total = collection.count_documents(query)
        products = list(
            collection.find(
                query,
                {
                    "_id": 1,
                    "category_id": 1,
                    "name": 1,
                    "description": 1,
                    "brand": 1,
                    "price": 1,
                    "currency": 1,
                    "status": 1,
                    "available_from": 1,
                    "available_to": 1,
                    "is_cold_start": 1,
                },
            )
            .sort([("_id", 1)])
            .skip(offset)
            .limit(limit)
        )
        category_ids = sorted(
            {product["category_id"] for product in products if product.get("category_id")}
        )
        categories = {
            category["_id"]: category
            for category in database["categories"].find(
                {"_id": {"$in": category_ids}},
                {"_id": 1, "name": 1, "slug": 1},
            )
        }
        for product in products:
            price = product.get("price")
            if hasattr(price, "to_decimal"):
                product["price"] = str(price.to_decimal())
            category = categories.get(product.get("category_id"))
            product["category"] = category
        return {
            "items": products,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except PyMongoError as exc:
        raise HTTPException(
            status_code=503, detail="Product data is unavailable in MongoDB."
        ) from exc


@router.get("/customers")
def list_customers(
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=25, ge=1, le=100),
    database: Any = Depends(get_catalog_database),
) -> list[dict[str, Any]]:
    query: dict[str, Any] = {}
    if search and search.strip():
        query["_id"] = {"$regex": re.escape(search.strip()), "$options": "i"}
    try:
        return list(
            database["customers"].find(
                query,
                {"_id": 1, "segment": 1, "region": 1, "is_active": 1},
            )
            .sort([("_id", 1)])
            .limit(limit)
        )
    except PyMongoError as exc:
        raise HTTPException(
            status_code=503, detail="Customer data is unavailable in MongoDB."
        ) from exc
