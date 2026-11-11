from dataclasses import dataclass
from typing import Any

from pymongo.database import Database

from backend.app.repositories.mongo import MongoRepository


@dataclass(frozen=True)
class ModelInputRepositories:
    customers: MongoRepository
    products: MongoRepository
    categories: MongoRepository
    sessions: MongoRepository
    page_views: MongoRepository
    carts: MongoRepository
    cart_lines: MongoRepository
    orders: MongoRepository
    order_lines: MongoRepository
    product_relations: MongoRepository
    recommendations: MongoRepository
    generation_runs: MongoRepository
    dataset_splits: MongoRepository
    model_runs: MongoRepository


def get_model_input_repositories(database: Database | Any) -> ModelInputRepositories:
    """Repositories for source/features; ground-truth labels are intentionally absent."""
    return ModelInputRepositories(
        customers=MongoRepository(database["customers"]),
        products=MongoRepository(database["products"]),
        categories=MongoRepository(database["categories"]),
        sessions=MongoRepository(database["sessions"]),
        page_views=MongoRepository(database["page_views"]),
        carts=MongoRepository(database["carts"]),
        cart_lines=MongoRepository(database["cart_lines"]),
        orders=MongoRepository(database["orders"]),
        order_lines=MongoRepository(database["order_lines"]),
        product_relations=MongoRepository(database["product_relations"]),
        recommendations=MongoRepository(database["recommendations"]),
        generation_runs=MongoRepository(database["generation_runs"]),
        dataset_splits=MongoRepository(database["dataset_splits"]),
        model_runs=MongoRepository(database["model_runs"]),
    )
