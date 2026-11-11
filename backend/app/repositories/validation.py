from dataclasses import dataclass
from typing import Any

from pymongo.database import Database

from backend.app.repositories.mongo import MongoRepository


@dataclass(frozen=True)
class ValidationRepositories:
    validation_issues: MongoRepository
    anomaly_fixtures: MongoRepository


def get_validation_repositories(
    database: Database | Any,
) -> ValidationRepositories:
    return ValidationRepositories(
        validation_issues=MongoRepository(database["validation_issues"]),
        anomaly_fixtures=MongoRepository(database["anomaly_fixtures"]),
    )
