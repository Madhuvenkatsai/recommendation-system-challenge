from copy import deepcopy
from datetime import timedelta
from typing import Any

from backend.app.generator.config import GenerationConfig
from backend.app.generator.engine import GenerationEngine
from backend.app.validation.engine import ValidationEngine


class CollectTarget:
    def __init__(self) -> None:
        self.records: dict[str, list[dict[str, Any]]] = {}
        self.issues: list[dict[str, Any]] = []

    def write_batch(self, *args) -> None:
        if len(args) == 2:
            collection_name, documents = args
            self.records.setdefault(collection_name, []).extend(deepcopy(documents))
            return
        documents = args[0]
        self.issues.extend(deepcopy(documents))

    def finalize(self, manifest: dict[str, Any]) -> None:
        return None

    def close(self) -> None:
        return None


def small_config() -> GenerationConfig:
    return GenerationConfig(
        customers=40,
        products=80,
        categories=8,
        sessions=60,
        orders=20,
    )


def generated_records() -> CollectTarget:
    target = CollectTarget()
    GenerationEngine(small_config(), batch_size=25).run(target)
    return target


def validate(records: CollectTarget) -> list[dict[str, Any]]:
    source = {
        name: rows
        for name, rows in records.records.items()
        if name != "validation_issues"
    }
    ValidationEngine().run(
        source,
        generation_run_id=records.records["generation_runs"][0]["_id"],
        target=records,
    )
    return records.issues


def test_generated_cart_and_order_histories_are_chronological_and_complete() -> None:
    records = generated_records()
    carts = {row["_id"]: row for row in records.records["carts"]}
    orders = {row["_id"]: row for row in records.records["orders"]}
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for event in records.records["lifecycle_events"]:
        grouped.setdefault((event["entity_type"], event["entity_id"]), []).append(event)

    assert len(grouped) == len(carts) + len(orders)
    for key, events in grouped.items():
        events.sort(key=lambda event: event["sequence"])
        assert [event["sequence"] for event in events] == list(
            range(1, len(events) + 1)
        )
        assert all(
            events[index]["occurred_at"] <= events[index + 1]["occurred_at"]
            for index in range(len(events) - 1)
        )
        assert events[0]["previous_state"] is None
        assert events[0]["event_type"] == "created"
        entity = carts[key[1]] if key[0] == "cart" else orders[key[1]]
        assert events[-1]["new_state"] == entity["status"]


def test_valid_generated_lifecycle_histories_pass_validation() -> None:
    records = generated_records()

    issues = validate(records)

    assert not any(
        issue["entity_type"] == "lifecycle_events"
        or issue["issue_type"].startswith("lifecycle_")
        for issue in issues
    )


def test_invalid_transition_and_out_of_order_timestamp_are_reported() -> None:
    records = generated_records()
    cart = next(row for row in records.records["carts"] if row["status"] != "active")
    history = [
        row
        for row in records.records["lifecycle_events"]
        if row["entity_type"] == "cart" and row["entity_id"] == cart["_id"]
    ]
    transition = next(row for row in history if row["sequence"] == 2)
    transition["previous_state"] = "converted"
    transition["occurred_at"] = history[0]["occurred_at"] - timedelta(seconds=1)

    issues = validate(records)

    assert any(issue["issue_type"] == "lifecycle_transition_invalid" for issue in issues)


def test_duplicate_lifecycle_event_sequence_is_reported() -> None:
    records = generated_records()
    duplicate = deepcopy(records.records["lifecycle_events"][0])
    duplicate["_id"] = "LCEDUPLICATE"
    records.records["lifecycle_events"].append(duplicate)

    issues = validate(records)

    assert any(issue["issue_type"] == "lifecycle_event_duplicate" for issue in issues)


def test_existing_history_is_not_mutated_by_validation() -> None:
    records = generated_records()
    original = deepcopy(records.records["lifecycle_events"])

    validate(records)

    assert records.records["lifecycle_events"] == original
