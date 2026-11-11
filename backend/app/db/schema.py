from copy import deepcopy
from typing import Any


def _field(bson_type: str | list[str], **constraints: Any) -> dict[str, Any]:
    return {"bsonType": bson_type, **constraints}


STRING_ID = _field("string", minLength=1)
STRING = _field("string", minLength=1)
OPTIONAL_STRING = _field(["string", "null"], minLength=1)
DATE = _field("date")
OPTIONAL_DATE = _field(["date", "null"])
INTEGER = _field("int", minimum=0)
POSITIVE_INTEGER = _field("int", minimum=1)
NUMBER = _field(["int", "long", "double", "decimal"], minimum=0)
METRIC = _field(
    ["int", "long", "double", "decimal", "null"], minimum=0, maximum=1
)
MONEY = _field("decimal", minimum=0)
BOOLEAN = _field("bool")
OBJECT = _field("object")
STRING_ARRAY = _field("array", items=STRING)

SCHEMAS: dict[str, dict[str, Any]] = {
    "customers": {
        "_id": STRING_ID,
        "created_at": DATE,
        "updated_at": DATE,
        "segment": OPTIONAL_STRING,
        "region": OPTIONAL_STRING,
        "attributes": OBJECT,
        "is_active": BOOLEAN,
    },
    "categories": {
        "_id": STRING_ID,
        "name": STRING,
        "slug": STRING,
        "parent_category_id": OPTIONAL_STRING,
        "seasonal_tags": STRING_ARRAY,
        "active_from": OPTIONAL_DATE,
        "active_to": OPTIONAL_DATE,
        "created_at": DATE,
        "updated_at": DATE,
    },
    "products": {
        "_id": STRING_ID,
        "category_id": OPTIONAL_STRING,
        "name": STRING,
        "description": _field("string"),
        "brand": OPTIONAL_STRING,
        "attributes": OBJECT,
        "price": MONEY,
        "currency": _field("string", pattern="^[A-Z]{3}$"),
        "status": _field(
            "string", enum=["active", "unavailable", "discontinued"]
        ),
        "available_from": OPTIONAL_DATE,
        "available_to": OPTIONAL_DATE,
        "is_cold_start": BOOLEAN,
        "created_at": DATE,
        "updated_at": DATE,
    },
    "sessions": {
        "_id": STRING_ID,
        "customer_id": STRING,
        "started_at": DATE,
        "ended_at": OPTIONAL_DATE,
        "source": OPTIONAL_STRING,
        "device": OPTIONAL_STRING,
        "is_bot": BOOLEAN,
        "is_noisy": BOOLEAN,
    },
    "page_views": {
        "_id": STRING_ID,
        "session_id": STRING,
        "customer_id": STRING,
        "product_id": STRING,
        "occurred_at": DATE,
        "sequence": POSITIVE_INTEGER,
        "referrer": OPTIONAL_STRING,
    },
    "carts": {
        "_id": STRING_ID,
        "customer_id": STRING,
        "session_id": OPTIONAL_STRING,
        "created_at": DATE,
        "updated_at": DATE,
        "converted_at": OPTIONAL_DATE,
        "status": _field(
            "string", enum=["active", "converted", "abandoned", "cancelled"]
        ),
    },
    "cart_lines": {
        "_id": STRING_ID,
        "cart_id": STRING,
        "product_id": STRING,
        "quantity": POSITIVE_INTEGER,
        "unit_price": MONEY,
        "line_total": MONEY,
        "added_at": DATE,
    },
    "orders": {
        "_id": STRING_ID,
        "customer_id": STRING,
        "session_id": OPTIONAL_STRING,
        "cart_id": OPTIONAL_STRING,
        "placed_at": DATE,
        "status": _field(
            "string",
            enum=["pending", "paid", "completed", "cancelled", "refunded"],
        ),
        "currency": _field("string", pattern="^[A-Z]{3}$"),
        "subtotal": MONEY,
        "discount_total": MONEY,
        "tax_total": MONEY,
        "shipping_total": MONEY,
        "total": MONEY,
    },
    "order_lines": {
        "_id": STRING_ID,
        "order_id": STRING,
        "product_id": STRING,
        "quantity": POSITIVE_INTEGER,
        "unit_price": MONEY,
        "discount": MONEY,
        "line_total": MONEY,
    },
    "product_relations": {
        "_id": STRING_ID,
        "source_product_id": STRING,
        "target_product_id": STRING,
        "relation_type": _field(
            "string",
            enum=["similar", "complementary", "substitute", "co_viewed"],
        ),
        "weight": NUMBER,
        "created_at": DATE,
    },
    "recommendations": {
        "_id": STRING_ID,
        "customer_id": STRING,
        "session_id": OPTIONAL_STRING,
        "model_run_id": OPTIONAL_STRING,
        "generation_run_id": OPTIONAL_STRING,
        "strategy": _field("string", enum=["popularity", "content", "hybrid"]),
        "k": POSITIVE_INTEGER,
        "model_version": STRING,
        "source_interaction_ids": STRING_ARRAY,
        "requested_at": DATE,
        "as_of_time": DATE,
        "training_cutoff": OPTIONAL_DATE,
        "purchased_exclusion_rule": STRING,
        "status": _field("string", enum=["valid", "anomaly_fixture"]),
        "items": _field(
            "array",
            items={
                "bsonType": "object",
                "required": ["product_id", "rank", "score"],
                "properties": {
                    "product_id": STRING,
                    "rank": POSITIVE_INTEGER,
                    "score": _field(["int", "long", "double", "decimal"]),
                    "reason": OPTIONAL_STRING,
                    "source_interaction_ids": STRING_ARRAY,
                    "eligibility_status": _field(
                        "string", enum=["eligible", "ineligible"]
                    ),
                },
                "additionalProperties": True,
            },
        ),
    },
    "generation_runs": {
        "_id": STRING_ID,
        "seed": _field("long", minimum=0),
        "configuration": OBJECT,
        "status": _field(
            "string",
            enum=["pending", "running", "completed", "failed", "interrupted"],
        ),
        "started_at": DATE,
        "completed_at": OPTIONAL_DATE,
        "collection_counts": OBJECT,
        "checksums": OBJECT,
        "error": OPTIONAL_STRING,
    },
    "validation_issues": {
        "_id": STRING_ID,
        "issue_id": STRING,
        "issue_type": STRING,
        "severity": _field("string", enum=["info", "warning", "error", "critical"]),
        "entity_type": STRING,
        "entity_id": OPTIONAL_STRING,
        "source_record_ids": STRING_ARRAY,
        "generation_run_id": STRING,
        "detected_at": DATE,
        "description": STRING,
        "ground_truth_label": STRING,
    },
    "anomaly_fixtures": {
        "_id": STRING_ID,
        "anomaly_id": STRING,
        "issue_type": _field(
            "string",
            enum=[
                "purchase_before_session_view",
                "missing_product_category",
                "train_test_leakage",
                "ineligible_product_recommendation",
            ],
        ),
        "severity": _field("string", enum=["warning", "error", "critical"]),
        "entity_type": STRING,
        "entity_id": STRING,
        "source_record_ids": STRING_ARRAY,
        "generation_run_id": STRING,
        "detected_at": DATE,
        "description": STRING,
        "ground_truth_label": STRING,
        "fixture_records": _field(
            "array",
            items={
                "bsonType": "object",
                "required": ["collection", "document"],
                "properties": {
                    "collection": STRING,
                    "document": OBJECT,
                    "assigned_split_id": OPTIONAL_STRING,
                },
                "additionalProperties": True,
            },
        ),
    },
    "dataset_splits": {
        "_id": STRING_ID,
        "dataset_version": STRING,
        "split_name": _field("string", enum=["train", "validation", "test"]),
        "start_at": DATE,
        "end_at": DATE,
        "created_at": DATE,
        "event_count": INTEGER,
    },
    "ground_truth_labels": {
        "_id": STRING_ID,
        "customer_id": STRING,
        "product_id": STRING,
        "source_event_id": STRING,
        "dataset_split_id": STRING,
        "event_type": _field("string", enum=["purchase", "view", "cart"]),
        "occurred_at": DATE,
        "relevance": NUMBER,
    },
    "model_runs": {
        "_id": STRING_ID,
        "algorithm": STRING,
        "model_version": STRING,
        "dataset_version": STRING,
        "training_split_id": STRING,
        "training_cutoff": DATE,
        "parameters": OBJECT,
        "feature_sources": STRING_ARRAY,
        "status": _field(
            "string", enum=["pending", "running", "completed", "failed"]
        ),
        "created_at": DATE,
        "completed_at": OPTIONAL_DATE,
    },
    "evaluation_results": {
        "_id": STRING_ID,
        "model_run_id": STRING,
        "dataset_split_id": STRING,
        "k": POSITIVE_INTEGER,
        "evaluated_at": DATE,
        "sample_count": INTEGER,
        "metrics": _field(
            "object",
            required=[
                "precision_at_k",
                "recall_at_k",
                "ndcg_at_k",
                "hit_rate_at_k",
                "catalog_coverage",
                "cold_start_coverage",
            ],
            properties={
                "precision_at_k": METRIC,
                "recall_at_k": METRIC,
                "ndcg_at_k": METRIC,
                "hit_rate_at_k": METRIC,
                "catalog_coverage": METRIC,
                "cold_start_coverage": METRIC,
            },
            additionalProperties=True,
        ),
    },
}

REQUIRED_FIELDS: dict[str, list[str]] = {
    "customers": ["_id", "created_at", "updated_at", "attributes", "is_active"],
    "categories": [
        "_id", "name", "slug", "seasonal_tags", "created_at", "updated_at",
    ],
    "products": [
        "_id", "name", "description", "attributes", "price", "currency",
        "status", "is_cold_start", "created_at", "updated_at",
    ],
    "sessions": [
        "_id", "customer_id", "started_at", "is_bot", "is_noisy",
    ],
    "page_views": [
        "_id", "session_id", "customer_id", "product_id", "occurred_at",
        "sequence",
    ],
    "carts": [
        "_id", "customer_id", "created_at", "updated_at", "status",
    ],
    "cart_lines": [
        "_id", "cart_id", "product_id", "quantity", "unit_price", "line_total",
        "added_at",
    ],
    "orders": [
        "_id", "customer_id", "placed_at", "status", "currency", "subtotal",
        "discount_total", "tax_total", "shipping_total", "total",
    ],
    "order_lines": [
        "_id", "order_id", "product_id", "quantity", "unit_price", "discount",
        "line_total",
    ],
    "product_relations": [
        "_id", "source_product_id", "target_product_id", "relation_type",
        "weight", "created_at",
    ],
    "recommendations": [
        "_id", "customer_id", "strategy", "model_version",
        "k", "source_interaction_ids", "requested_at", "as_of_time",
        "purchased_exclusion_rule", "status", "items",
    ],
    "generation_runs": [
        "_id", "seed", "configuration", "status", "started_at", "completed_at",
        "collection_counts", "checksums", "error",
    ],
    "validation_issues": [
        "_id", "issue_id", "issue_type", "severity", "entity_type", "entity_id",
        "source_record_ids", "generation_run_id", "detected_at", "description",
        "ground_truth_label",
    ],
    "anomaly_fixtures": [
        "_id", "anomaly_id", "issue_type", "severity", "entity_type",
        "entity_id", "source_record_ids", "generation_run_id", "detected_at",
        "description", "ground_truth_label", "fixture_records",
    ],
    "dataset_splits": [
        "_id", "dataset_version", "split_name", "start_at", "end_at",
        "created_at", "event_count",
    ],
    "ground_truth_labels": [
        "_id", "customer_id", "product_id", "source_event_id",
        "dataset_split_id", "event_type", "occurred_at", "relevance",
    ],
    "model_runs": [
        "_id", "algorithm", "model_version", "dataset_version",
        "training_split_id", "training_cutoff", "parameters", "feature_sources",
        "status", "created_at", "completed_at",
    ],
    "evaluation_results": [
        "_id", "model_run_id", "dataset_split_id", "k", "evaluated_at",
        "sample_count", "metrics",
    ],
}


def validator_for(collection_name: str) -> dict[str, Any]:
    """Return a fresh MongoDB $jsonSchema validator for a collection."""
    properties = SCHEMAS[collection_name]
    return {
        "$jsonSchema": {
            "bsonType": "object",
            "required": REQUIRED_FIELDS[collection_name],
            "properties": deepcopy(properties),
            "additionalProperties": True,
        }
    }


# Index key tuples are passed directly to PyMongo create_index.
INDEXES: dict[str, list[dict[str, Any]]] = {
    "customers": [
        {"keys": [("is_active", 1)], "name": "is_active"},
    ],
    "categories": [
        {"keys": [("slug", 1)], "name": "slug_unique", "unique": True},
        {"keys": [("parent_category_id", 1)], "name": "parent_category_id"},
    ],
    "products": [
        {"keys": [("category_id", 1), ("status", 1)], "name": "category_status"},
        {"keys": [("status", 1), ("available_from", 1), ("available_to", 1)], "name": "status_availability"},
    ],
    "sessions": [
        {"keys": [("customer_id", 1), ("started_at", -1)], "name": "customer_started_at"},
        {"keys": [("started_at", 1)], "name": "started_at"},
    ],
    "page_views": [
        {"keys": [("session_id", 1), ("sequence", 1)], "name": "session_sequence", "unique": True},
        {"keys": [("customer_id", 1), ("occurred_at", 1)], "name": "customer_occurred_at"},
        {"keys": [("product_id", 1), ("occurred_at", 1)], "name": "product_occurred_at"},
    ],
    "carts": [
        {"keys": [("customer_id", 1), ("created_at", -1)], "name": "customer_created_at"},
        {"keys": [("session_id", 1)], "name": "session_id"},
    ],
    "cart_lines": [
        {"keys": [("cart_id", 1), ("product_id", 1)], "name": "cart_product_unique", "unique": True},
        {"keys": [("product_id", 1)], "name": "product_id"},
    ],
    "orders": [
        {"keys": [("customer_id", 1), ("placed_at", -1)], "name": "customer_placed_at"},
        {"keys": [("cart_id", 1)], "name": "cart_id"},
        {"keys": [("status", 1), ("placed_at", 1)], "name": "status_placed_at"},
    ],
    "order_lines": [
        {"keys": [("order_id", 1), ("product_id", 1)], "name": "order_product_unique", "unique": True},
        {"keys": [("product_id", 1)], "name": "product_id"},
    ],
    "product_relations": [
        {"keys": [("source_product_id", 1), ("target_product_id", 1), ("relation_type", 1)], "name": "directed_relation_unique", "unique": True},
        {"keys": [("target_product_id", 1)], "name": "target_product_id"},
    ],
    "recommendations": [
        {"keys": [("customer_id", 1), ("requested_at", -1)], "name": "customer_requested_at"},
        {"keys": [("model_run_id", 1)], "name": "model_run_id"},
    ],
    "generation_runs": [
        {"keys": [("status", 1), ("started_at", -1)], "name": "status_started_at"},
    ],
    "validation_issues": [
        {
            "keys": [("issue_id", 1)],
            "name": "issue_id_unique",
            "unique": True,
            "sparse": True,
        },
        {"keys": [("generation_run_id", 1), ("severity", 1)], "name": "run_severity"},
        {"keys": [("issue_type", 1), ("entity_id", 1)], "name": "issue_entity"},
    ],
    "anomaly_fixtures": [
        {"keys": [("anomaly_id", 1)], "name": "anomaly_id_unique", "unique": True},
        {"keys": [("generation_run_id", 1), ("issue_type", 1)], "name": "run_issue_type"},
    ],
    "dataset_splits": [
        {"keys": [("dataset_version", 1), ("split_name", 1)], "name": "dataset_split_unique", "unique": True},
    ],
    "ground_truth_labels": [
        {"keys": [("source_event_id", 1)], "name": "source_event_id_unique", "unique": True},
        {"keys": [("dataset_split_id", 1), ("customer_id", 1), ("product_id", 1), ("occurred_at", 1)], "name": "split_customer_product_time"},
        {"keys": [("customer_id", 1), ("occurred_at", 1)], "name": "customer_occurred_at"},
    ],
    "model_runs": [
        {"keys": [("dataset_version", 1), ("created_at", -1)], "name": "dataset_created_at"},
        {"keys": [("training_split_id", 1)], "name": "training_split_id"},
    ],
    "evaluation_results": [
        {"keys": [("model_run_id", 1), ("dataset_split_id", 1), ("k", 1)], "name": "model_split_k_unique", "unique": True},
    ],
}

CORE_COLLECTIONS = (
    "customers",
    "products",
    "categories",
    "sessions",
    "page_views",
    "carts",
    "cart_lines",
    "orders",
    "order_lines",
    "product_relations",
    "recommendations",
)

SUPPORTING_COLLECTIONS = (
    "generation_runs",
    "validation_issues",
    "anomaly_fixtures",
    "dataset_splits",
    "ground_truth_labels",
    "model_runs",
    "evaluation_results",
)

COLLECTION_NAMES = CORE_COLLECTIONS + SUPPORTING_COLLECTIONS
