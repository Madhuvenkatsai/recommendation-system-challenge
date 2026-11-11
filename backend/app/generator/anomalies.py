from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Iterator

from backend.app.generator.config import GenerationConfig
from backend.app.generator.ids import dataset_fingerprint, dataset_id, make_id
from backend.app.generator.records import (
    _order_line_records,
    _order_record,
    _product_record,
    _session_record,
    _split_records,
    _unavailable_start,
)

ANOMALY_TYPES = (
    "purchase_before_session_view",
    "missing_product_category",
    "train_test_leakage",
    "ineligible_product_recommendation",
)


@dataclass(frozen=True)
class AnomalyConfig:
    enabled: bool = False
    issue_types: tuple[str, ...] = ANOMALY_TYPES

    def __post_init__(self) -> None:
        unknown = set(self.issue_types) - set(ANOMALY_TYPES)
        if unknown:
            raise ValueError(f"Unknown anomaly types: {', '.join(sorted(unknown))}.")
        if len(set(self.issue_types)) != len(self.issue_types):
            raise ValueError("Anomaly issue types must be unique.")


def _anomaly_id(config: GenerationConfig, issue_type: str) -> str:
    fingerprint = dataset_fingerprint(config.as_dict())
    return f"ANM{fingerprint}{issue_type.upper()}"


def _fixture_document(
    config: GenerationConfig,
    issue_type: str,
    entity_type: str,
    entity_id: str,
    source_record_ids: list[str],
    fixture_records: list[dict[str, Any]],
    description: str,
    *,
    severity: str = "critical",
) -> dict[str, Any]:
    anomaly_id = _anomaly_id(config, issue_type)
    run_fingerprint = dataset_fingerprint(config.as_dict())
    return {
        "_id": f"ANF{run_fingerprint}{issue_type.upper()}",
        "anomaly_id": anomaly_id,
        "issue_type": issue_type,
        "severity": severity,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "source_record_ids": source_record_ids,
        "generation_run_id": dataset_id("generation_runs", run_fingerprint, ""),
        "detected_at": config.end_at,
        "description": description,
        "ground_truth_label": issue_type,
        "fixture_records": fixture_records,
    }


def iter_anomaly_fixtures(
    config: GenerationConfig, anomaly_config: AnomalyConfig
) -> Iterator[dict[str, Any]]:
    if not anomaly_config.enabled:
        return

    if "purchase_before_session_view" in anomaly_config.issue_types:
        session = _session_record(config, 0)
        order = _order_record(config, 0)
        line = next(_order_line_records(config, 0))
        source_order_id = order["_id"]
        source_line_id = line["_id"]
        order["placed_at"] = session["started_at"] + timedelta(minutes=1)
        order_id = f"{order['_id']}ANM"
        line_id = f"{line['_id']}ANM"
        order["_id"] = order_id
        line["_id"] = line_id
        line["order_id"] = order_id
        yield _fixture_document(
            config,
            "purchase_before_session_view",
            "orders",
            order_id,
            [
                session["_id"],
                source_order_id,
                source_line_id,
                order_id,
                line_id,
                line["product_id"],
            ],
            [
                {"collection": "sessions", "document": session},
                {"collection": "orders", "document": order},
                {"collection": "order_lines", "document": line},
            ],
            "Order placement precedes every product view in its associated session.",
        )

    if "missing_product_category" in anomaly_config.issue_types:
        product = _product_record(config, 0)
        source_product_id = product["_id"]
        product_id = f"{product['_id']}ANM"
        product["_id"] = product_id
        product["category_id"] = "CAT_MISSING_ANOMALY"
        yield _fixture_document(
            config,
            "missing_product_category",
            "products",
            product_id,
            [source_product_id, product_id, product["category_id"]],
            [{"collection": "products", "document": product}],
            "Product category_id references a category that does not exist.",
            severity="error",
        )

    if "train_test_leakage" in anomaly_config.issue_types:
        order_index = config.orders - 1
        order = _order_record(config, order_index)
        source_order_id = order["_id"]
        order_id = f"{order['_id']}LEAK"
        order["_id"] = order_id
        splits = list(_split_records(config, {"train": 0, "validation": 0, "test": 0}))
        train_split = next(row for row in splits if row["split_name"] == "train")
        yield _fixture_document(
            config,
            "train_test_leakage",
            "orders",
            order_id,
            [source_order_id, order_id, order["session_id"], train_split["_id"]],
            [
                {
                    "collection": "orders",
                    "document": order,
                    "assigned_split_id": train_split["_id"],
                }
            ],
            "Test-period order is incorrectly assigned to the train split.",
        )

    if "ineligible_product_recommendation" in anomaly_config.issue_types:
        product_index = max(_unavailable_start(config), config.products - 1)
        product_index = min(product_index, config.products - 1)
        product = _product_record(config, product_index)
        product_id = product["_id"]
        recommendation_id = f"REC{dataset_fingerprint(config.as_dict())}ANOMALY"
        as_of_time = config.end_at - timedelta(days=1)
        recommendation = {
            "_id": recommendation_id,
            "customer_id": make_id("customers", 0, config.customers),
            "requested_at": as_of_time,
            "as_of_time": as_of_time,
            "purchased_exclusion_rule": "exclude_prior_completed_purchases",
            "status": "anomaly_fixture",
            "items": [{"product_id": product_id, "rank": 1, "score": 1.0}],
        }
        yield _fixture_document(
            config,
            "ineligible_product_recommendation",
            "recommendations",
            recommendation_id,
            [recommendation_id, product_id],
            [
                {"collection": "products", "document": product},
                {"collection": "recommendations", "document": recommendation},
            ],
            "Recommendation contains a product discontinued or unavailable at as_of_time.",
        )
