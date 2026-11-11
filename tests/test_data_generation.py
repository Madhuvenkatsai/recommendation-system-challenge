import csv
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

from bson import BSON
from bson.decimal128 import Decimal128
import pytest

from backend.app.db.schema import COLLECTION_NAMES, REQUIRED_FIELDS, SCHEMAS
from backend.app.generator.config import GenerationConfig, GENERATION_SEED
from backend.app.generator.engine import GenerationEngine
from backend.app.generator.ids import ID_PREFIXES
from backend.app.generator.records import page_view_count_for_session
from backend.app.generator.targets import (
    ExportGenerationTarget,
    MongoGenerationTarget,
)


class CollectTarget:
    def __init__(self) -> None:
        self.records: dict[str, list[dict[str, Any]]] = {
            name: [] for name in COLLECTION_NAMES
        }
        self.batch_sizes: list[int] = []
        self.manifest: dict[str, Any] | None = None
        self.closed = False

    def write_batch(
        self, collection_name: str, documents: list[dict[str, Any]]
    ) -> None:
        self.records[collection_name].extend(documents)
        self.batch_sizes.append(len(documents))

    def finalize(self, manifest: dict[str, Any]) -> None:
        self.manifest = manifest

    def close(self) -> None:
        self.closed = True


class FakeMongoCollection:
    def __init__(self) -> None:
        self.inserted: list[dict[str, Any]] = []

    def insert_many(self, documents: list[dict[str, Any]], *, ordered: bool):
        assert ordered
        self.inserted.extend(documents)
        return object()


class FakeMongoDatabase:
    def __init__(self) -> None:
        self.collections: dict[str, FakeMongoCollection] = {}

    def __getitem__(self, collection_name: str) -> FakeMongoCollection:
        return self.collections.setdefault(collection_name, FakeMongoCollection())


def small_config() -> GenerationConfig:
    return GenerationConfig(
        customers=40,
        products=80,
        categories=8,
        sessions=60,
        orders=20,
    )


def generate(
    config: GenerationConfig | None = None, batch_size: int = 17
) -> tuple[CollectTarget, Any]:
    target = CollectTarget()
    manifest = GenerationEngine(config or small_config(), batch_size=batch_size).run(
        target
    )
    return target, manifest


def _decimal(value: Decimal128) -> int:
    return int(value.to_decimal() * 100)


def test_full_and_starter_configs_use_required_targets_and_fixed_seed() -> None:
    full = GenerationConfig.full()
    starter = GenerationConfig.starter()

    assert full.seed == GENERATION_SEED == 20261022
    assert (full.customers, full.products, full.sessions, full.orders) == (
        20_000,
        10_000,
        500_000,
        100_000,
    )
    assert full.cart_count == 250_000
    assert (starter.customers, starter.products, starter.sessions, starter.orders) == (
        200,
        100,
        2_500,
        500,
    )
    assert full.as_dict()["seed"] == starter.as_dict()["seed"] == 20261022


def test_generation_is_reproducible_and_respects_bounded_batches() -> None:
    first, first_manifest = generate(batch_size=17)
    second, second_manifest = generate(batch_size=17)

    assert first_manifest.collection_counts == second_manifest.collection_counts
    assert first_manifest.checksums == second_manifest.checksums
    assert first.records.keys() == second.records.keys()
    for collection_name in COLLECTION_NAMES:
        if collection_name != "generation_runs":
            assert first.records[collection_name] == second.records[collection_name]
    assert first.batch_sizes
    assert max(first.batch_sizes) <= 17
    assert first.closed and second.closed


def test_row_counts_are_exact_or_deterministically_derived() -> None:
    target, manifest = generate()
    counts = manifest.collection_counts
    config = small_config()

    assert counts["categories"] == config.categories
    assert counts["customers"] == config.customers
    assert counts["products"] == config.products
    assert counts["sessions"] == config.sessions
    assert counts["page_views"] == sum(
        page_view_count_for_session(config, index)
        for index in range(config.sessions)
    )
    assert config.sessions <= counts["page_views"] <= config.sessions * 5
    assert counts["carts"] == config.cart_count
    assert counts["cart_lines"] == len(target.records["cart_lines"])
    assert config.cart_count <= counts["cart_lines"] <= config.cart_count * 3
    assert counts["orders"] == config.orders
    assert counts["order_lines"] == len(target.records["order_lines"])
    assert config.orders <= counts["order_lines"] <= config.orders * 3
    assert counts["product_relations"] == 2 * 72
    assert counts["dataset_splits"] == 3
    assert counts["ground_truth_labels"] == len(target.records["ground_truth_labels"])
    assert counts["generation_runs"] == 1
    assert counts["recommendations"] == 0
    assert set(counts) == set(COLLECTION_NAMES)
    assert set(manifest.checksums) == set(COLLECTION_NAMES) - {"generation_runs"}


def test_interaction_depth_and_product_popularity_are_skewed() -> None:
    target, _ = generate()
    view_counts: dict[str, int] = {}
    product_indices = []
    for row in target.records["page_views"]:
        view_counts[row["session_id"]] = view_counts.get(row["session_id"], 0) + 1
        product_indices.append(int(row["product_id"][3:]) - 1)

    assert min(view_counts.values()) == 1
    assert max(view_counts.values()) == 5
    assert len(set(view_counts.values())) > 1
    assert sum(product_indices) / len(product_indices) < 32


def test_generated_ids_use_documented_formats() -> None:
    target, _ = generate()

    for collection_name, records in target.records.items():
        ids = [row["_id"] for row in records]
        assert len(ids) == len(set(ids))
        prefix = ID_PREFIXES.get(collection_name)
        if collection_name == "dataset_splits":
            assert all(re.fullmatch(r"SPL[0-9A-F]{16}(TRAIN|VALIDATION|TEST)", row["_id"]) for row in records)
        elif collection_name == "generation_runs":
            assert all(re.fullmatch(r"RUN[0-9A-F]{16}", row["_id"]) for row in records)
        elif prefix:
            assert all(
                re.fullmatch(rf"{prefix}\d{{8,}}", row["_id"]) for row in records
            )

    with pytest.raises(ValueError, match="fixed at"):
        GenerationConfig(seed=7)


def test_generated_documents_match_schema_fields_and_encode_as_bson() -> None:
    target, _ = generate()

    for collection_name, records in target.records.items():
        properties = set(SCHEMAS[collection_name])
        for record in records:
            assert set(REQUIRED_FIELDS[collection_name]) <= set(record)
            assert set(record) <= properties
            BSON.encode(record)


def test_foreign_keys_chronology_lifecycle_and_money_are_consistent() -> None:
    target, _ = generate()
    rows = target.records
    customers = {row["_id"] for row in rows["customers"]}
    categories = {row["_id"] for row in rows["categories"]}
    products = {row["_id"]: row for row in rows["products"]}
    sessions = {row["_id"]: row for row in rows["sessions"]}
    carts = {row["_id"]: row for row in rows["carts"]}
    orders = {row["_id"]: row for row in rows["orders"]}
    views_by_session_product = {
        (row["session_id"], row["product_id"]): row["occurred_at"]
        for row in rows["page_views"]
    }

    for category in rows["categories"]:
        parent_id = category["parent_category_id"]
        assert parent_id is None or parent_id in categories
    for product in products.values():
        assert product["category_id"] in categories
    cold_start_ids = {
        product["_id"] for product in products.values() if product["is_cold_start"]
    }
    assert cold_start_ids
    assert not any(row["product_id"] in cold_start_ids for row in rows["page_views"])
    assert not any(
        row["product_id"] in cold_start_ids for row in rows["order_lines"]
    )
    assert {product["status"] for product in products.values()} == {
        "active",
        "unavailable",
        "discontinued",
    }
    for product in products.values():
        expected_group = (
            "cold_start"
            if product["is_cold_start"]
            else product["status"]
            if product["status"] != "active"
            else "popular"
        )
        assert product["attributes"]["catalog_group"] == expected_group
    seasonal_tags = {
        tag for category in rows["categories"] for tag in category["seasonal_tags"]
    }
    assert seasonal_tags == {"spring", "summer", "autumn", "winter"}
    for session in sessions.values():
        assert session["customer_id"] in customers
        assert session["started_at"] < session["ended_at"]

    previous_start: datetime | None = None
    for session in rows["sessions"]:
        if previous_start is not None:
            assert session["started_at"] >= previous_start
        previous_start = session["started_at"]
    assert any(session["is_bot"] for session in sessions.values())
    assert any(session["is_noisy"] for session in sessions.values())
    assert any(
        customer["attributes"]["activity_tier"] == "sparse"
        for customer in rows["customers"]
    )
    sessions_per_customer: dict[str, int] = {}
    for session in sessions.values():
        sessions_per_customer[session["customer_id"]] = (
            sessions_per_customer.get(session["customer_id"], 0) + 1
        )
    sparse_customer_ids = {
        row["_id"]
        for row in rows["customers"]
        if row["attributes"]["activity_tier"] == "sparse"
    }
    regular_customer_ids = customers - sparse_customer_ids
    sparse_mean = sum(
        sessions_per_customer.get(customer_id, 0)
        for customer_id in sparse_customer_ids
    ) / len(sparse_customer_ids)
    regular_mean = sum(
        sessions_per_customer.get(customer_id, 0)
        for customer_id in regular_customer_ids
    ) / len(regular_customer_ids)
    assert sparse_mean < regular_mean
    assert len(sessions_per_customer) < len(customers)

    for page_view in rows["page_views"]:
        session = sessions[page_view["session_id"]]
        assert page_view["customer_id"] == session["customer_id"]
        assert page_view["product_id"] in products
        assert session["started_at"] <= page_view["occurred_at"] <= session["ended_at"]

    lines_by_cart: dict[str, list[dict[str, Any]]] = {}
    for line in rows["cart_lines"]:
        lines_by_cart.setdefault(line["cart_id"], []).append(line)
        assert line["cart_id"] in carts
        assert line["product_id"] in products
        assert _decimal(line["line_total"]) == _decimal(line["unit_price"]) * line["quantity"]

    orders_by_cart = {order["cart_id"]: order for order in rows["orders"]}
    for cart in rows["carts"]:
        assert cart["customer_id"] in customers
        assert cart["session_id"] in sessions
        assert lines_by_cart[cart["_id"]]
        for line in lines_by_cart[cart["_id"]]:
            view_at = views_by_session_product[
                (cart["session_id"], line["product_id"])
            ]
            assert view_at < line["added_at"]
        if cart["_id"] in orders_by_cart:
            order = orders_by_cart[cart["_id"]]
            assert cart["status"] == "converted"
            assert order["placed_at"] > cart["created_at"]
            assert order["placed_at"] <= sessions[cart["session_id"]]["ended_at"]
        else:
            assert cart["status"] in {"active", "abandoned"}
            assert cart["converted_at"] is None

    lines_by_order: dict[str, list[dict[str, Any]]] = {}
    for line in rows["order_lines"]:
        lines_by_order.setdefault(line["order_id"], []).append(line)
        assert line["order_id"] in orders
        assert line["product_id"] in products
        assert line["discount"].to_decimal() == 0
        assert _decimal(line["line_total"]) == _decimal(line["unit_price"]) * line["quantity"]

    for order in rows["orders"]:
        lines = lines_by_order[order["_id"]]
        assert lines
        cart_lines = lines_by_cart[order["cart_id"]]
        assert {
            (line["product_id"], line["quantity"]) for line in lines
        } == {
            (line["product_id"], line["quantity"]) for line in cart_lines
        }
        subtotal = sum(_decimal(line["line_total"]) for line in lines)
        expected_tax = (subtotal + 5) // 10
        expected_shipping = 0 if subtotal >= 10_000 else 500
        assert _decimal(order["subtotal"]) == subtotal
        assert _decimal(order["total"]) == subtotal + expected_tax + expected_shipping
        assert order["status"] in {"completed", "cancelled", "refunded"}
        assert order["placed_at"] > max(
            views_by_session_product[(order["session_id"], line["product_id"])]
            for line in lines
        )

    for relation in rows["product_relations"]:
        source = products[relation["source_product_id"]]
        target_product = products[relation["target_product_id"]]
        assert source["status"] == target_product["status"] == "active"
        if relation["relation_type"] == "similar":
            assert source["category_id"] == target_product["category_id"]
        else:
            assert relation["relation_type"] == "complementary"
            assert source["category_id"] != target_product["category_id"]
        assert source["_id"] != target_product["_id"]


def test_ground_truth_is_held_out_and_separate_from_model_inputs() -> None:
    target, manifest = generate()
    rows = target.records
    split_by_id = {row["_id"]: row for row in rows["dataset_splits"]}
    order_lines = {row["_id"]: row for row in rows["order_lines"]}
    orders_by_id = {row["_id"]: row for row in rows["orders"]}
    order_by_line = {
        line["_id"]: orders_by_id[line["order_id"]]
        for line in rows["order_lines"]
    }

    assert {row["split_name"] for row in split_by_id.values()} == {
        "train",
        "validation",
        "test",
    }
    for label in rows["ground_truth_labels"]:
        source = order_lines[label["source_event_id"]]
        order = order_by_line[label["source_event_id"]]
        split = split_by_id[label["dataset_split_id"]]
        assert split["split_name"] in {"validation", "test"}
        assert label["event_type"] == "purchase"
        assert label["customer_id"] == order["customer_id"]
        assert label["product_id"] == source["product_id"]
        assert label["occurred_at"] == order["placed_at"]
        assert order["status"] == "completed"
        assert split["start_at"] <= label["occurred_at"] < split["end_at"]

    assert manifest.collection_counts["ground_truth_labels"] > 0
    assert sum(row["event_count"] for row in split_by_id.values()) == (
        manifest.collection_counts["page_views"]
        + manifest.collection_counts["carts"]
        + manifest.collection_counts["orders"]
    )
    assert all(
        target.records["ground_truth_labels"]
    )


def test_exports_are_written_as_csv_jsonl_and_manifest() -> None:
    output_dir = Path(
        tempfile.mkdtemp(prefix=".generator-export-test-", dir=Path(__file__).parent)
    )
    try:
        export_target = ExportGenerationTarget(output_dir)
        manifest = GenerationEngine(small_config(), batch_size=31).run(export_target)

        assert (output_dir / "customers.csv").is_file()
        assert (output_dir / "orders.jsonl").is_file()
        assert (output_dir / "recommendations.csv").is_file()
        with (output_dir / "customers.csv").open(
            encoding="utf-8", newline=""
        ) as csv_file:
            customer_rows = list(csv.DictReader(csv_file))
        with (output_dir / "orders.jsonl").open(encoding="utf-8") as jsonl_file:
            order_rows = [json.loads(line) for line in jsonl_file]
        saved_manifest = json.loads(
            (output_dir / "manifest.json").read_text(encoding="utf-8")
        )
        assert len(customer_rows) == small_config().customers
        assert len(order_rows) == small_config().orders
        assert saved_manifest["checksums"] == manifest.checksums
        assert saved_manifest["collection_counts"] == manifest.collection_counts
    finally:
        shutil.rmtree(output_dir)


def test_mongo_target_writes_ground_truth_through_evaluation_repository() -> None:
    database = FakeMongoDatabase()
    target = MongoGenerationTarget(database)
    label = {
        "_id": "GTL00000001",
        "customer_id": "CUS00000001",
        "product_id": "PRO00000001",
        "source_event_id": "OLN00000001",
        "dataset_split_id": "SPL0123456789ABCDEFTEST",
        "event_type": "purchase",
    }

    target.write_batch("ground_truth_labels", [label])

    assert database["ground_truth_labels"].inserted == [label]
    assert database["orders"].inserted == []
