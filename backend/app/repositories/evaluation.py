from dataclasses import dataclass
from typing import Any

from pymongo.database import Database

from backend.app.repositories.mongo import MongoRepository


@dataclass(frozen=True)
class EvaluationRepositories:
    ground_truth_labels: MongoRepository
    dataset_splits: MongoRepository
    evaluation_results: MongoRepository
    model_runs: MongoRepository


def get_evaluation_repositories(database: Database | Any) -> EvaluationRepositories:
    """Evaluation-only access to labels, isolated from model input repositories."""
    return EvaluationRepositories(
        ground_truth_labels=MongoRepository(database["ground_truth_labels"]),
        dataset_splits=MongoRepository(database["dataset_splits"]),
        evaluation_results=MongoRepository(database["evaluation_results"]),
        model_runs=MongoRepository(database["model_runs"]),
    )
