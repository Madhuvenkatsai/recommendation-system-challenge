from copy import deepcopy
import csv
import json
from typing import Any

from bson.decimal128 import Decimal128

from backend.app.db.schema import COLLECTION_NAMES, CORE_COLLECTIONS
from backend.app.generator.anomalies import ANOMALY_TYPES, AnomalyConfig
from backend.app.generator.engine import GenerationEngine
from backend.app.generator.config import GenerationConfig
from backend.app.validation.engine import ValidationEngine
from backend.app.validation.targets import ValidationExportTarget


class CollectIssues:
    def __init__(self) -> None:
        self.issues: list[dict[str, Any]] = []
        self.report: dict[str, Any] | None = None
        self.batch_sizes: list[int] = []
        self.closed = False

    def write_batch(self, documents: list[dict[str, Any]]) -> None:
        self.issues.extend(deepcopy(documents))
        self.batch_sizes.append(len(documents))

    def finalize(self, report: dict[str, Any]) -> None:
        self.report = deepcopy(report)

    def close(self) -> None:
        self.closed = True


class CollectTarget:
    def __init__(self) -> None:
        self.records: dict[str, list[dict[str, Any]]] = {
            name: [] for name in COLLECTION_NAMES
        }

    def write_batch(
        self, collection_name: str, documents: list[dict[str, Any]]
    ) -> None:
        self.records[collection_name].extend(deepcopy(documents))

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


def generate(*, anomalies: bool) -> CollectTarget:
    target = CollectTarget()
    GenerationEngine(
        small_config(),
        batch_size=13,
        anomaly_config=AnomalyConfig(enabled=anomalies),
    ).run(target)
    return target


def validate(source: CollectTarget) -> tuple[CollectIssues, dict[str, Any]]:
    target = CollectIssues()
    run_id = source.records["generation_runs"][0]["_id"]
    sources = {
        name: rows
        for name, rows in source.records.items()
        if name != "validation_issues"
    }
    report = ValidationEngine(batch_size=7).run(
        sources,
        generation_run_id=run_id,
        target=target,
    )
    assert target.report == report.as_dict()
    assert target.closed
    return target, report.as_dict()


def test_clean_generated_baseline_passes_all_validators() -> None:
    clean = generate(anomalies=False)

    issues, report = validate(clean)

    assert issues.issues == []
    assert report["issue_count"] == 0
    assert report["clean_record_count"] == sum(
        len(clean.records[name]) for name in CORE_COLLECTIONS
    )
    assert report["anomalous_record_count"] == 0


def test_all_four_anomaly_fixtures_are_detected_and_traced() -> None:
    anomalous = generate(anomalies=True)

    issues, report = validate(anomalous)

    assert {row["issue_type"] for row in anomalous.records["anomaly_fixtures"]} == set(
        ANOMALY_TYPES
    )
    detected = {row["ground_truth_label"] for row in issues.issues}
    assert set(ANOMALY_TYPES) <= detected
    assert report["anomalous_record_count"] == sum(
        len(row["fixture_records"])
        for row in anomalous.records["anomaly_fixtures"]
    )
    assert all(row["generation_run_id"] for row in issues.issues)
    assert all(row["source_record_ids"] for row in issues.issues)
    assert all(row["detected_at"].year == 2026 for row in issues.issues)
    assert max(issues.batch_sizes) <= 7


def test_anomaly_generation_is_reproducible_without_modifying_clean_records() -> None:
    baseline = generate(anomalies=False)
    first = generate(anomalies=True)
    second = generate(anomalies=True)

    for collection in COLLECTION_NAMES:
        if collection not in {"generation_runs", "anomaly_fixtures"}:
            assert first.records[collection] == baseline.records[collection]
            assert first.records[collection] == second.records[collection]
    assert first.records["anomaly_fixtures"] == second.records["anomaly_fixtures"]


def test_validation_results_and_ids_are_deterministic() -> None:
    source = generate(anomalies=True)

    first, first_report = validate(source)
    second, second_report = validate(source)

    assert first.issues == second.issues
    assert first_report == second_report
    assert len({row["issue_id"] for row in first.issues}) == len(first.issues)


def test_cross_collection_reference_and_primary_key_violations_are_detected() -> None:
    source = generate(anomalies=False)
    source.records["page_views"][0]["product_id"] = "PRO_DOES_NOT_EXIST"
    source.records["page_views"][0].pop("occurred_at")
    duplicate = deepcopy(source.records["customers"][0])
    source.records["customers"].append(duplicate)

    issues, _ = validate(source)

    assert any(
        issue["issue_type"] == "foreign_reference_missing"
        and "PRO_DOES_NOT_EXIST" in issue["source_record_ids"]
        for issue in issues.issues
    )
    assert any(
        issue["issue_type"] == "primary_key_duplicate"
        and issue["entity_type"] == "customers"
        for issue in issues.issues
    )
    assert any(
        issue["issue_type"] == "required_field_missing"
        and issue["entity_type"] == "page_views"
        for issue in issues.issues
    )


def test_chronology_and_leakage_fixtures_are_detected() -> None:
    source = generate(anomalies=True)

    issues, _ = validate(source)

    assert any(row["issue_type"] == "purchase_before_session_view" for row in issues.issues)
    assert any(row["issue_type"] == "train_test_leakage" for row in issues.issues)


def test_arithmetic_hierarchy_and_duplicate_events_are_detected() -> None:
    source = generate(anomalies=False)
    source.records["cart_lines"][0]["line_total"] = Decimal128("0.01")
    source.records["categories"][0]["parent_category_id"] = source.records[
        "categories"
    ][0]["_id"]
    duplicate_view = deepcopy(source.records["page_views"][0])
    duplicate_view["_id"] = "PVWDUPLICATE"
    source.records["page_views"].append(duplicate_view)

    issues, _ = validate(source)

    issue_types = {row["issue_type"] for row in issues.issues}
    assert "cart_line_arithmetic_invalid" in issue_types
    assert "category_hierarchy_cycle" in issue_types
    assert "duplicate_event" in issue_types


def test_anomaly_types_can_be_selected_independently() -> None:
    target = CollectTarget()
    GenerationEngine(
        small_config(),
        anomaly_config=AnomalyConfig(
            enabled=True,
            issue_types=("missing_product_category",),
        ),
    ).run(target)

    assert [
        row["issue_type"] for row in target.records["anomaly_fixtures"]
    ] == ["missing_product_category"]


def test_validation_writes_issue_exports_and_summary(tmp_path) -> None:
    source = generate(anomalies=True)
    output = tmp_path / "validation"
    run_id = source.records["generation_runs"][0]["_id"]
    sources = {
        name: rows
        for name, rows in source.records.items()
        if name != "validation_issues"
    }

    report = ValidationEngine().run(
        sources,
        generation_run_id=run_id,
        target=ValidationExportTarget(output),
    )

    with (output / "validation_issues.csv").open(
        encoding="utf-8", newline=""
    ) as issue_file:
        rows = list(csv.DictReader(issue_file))
    with (output / "validation_issues.jsonl").open(encoding="utf-8") as issue_file:
        jsonl_rows = [json.loads(line) for line in issue_file]
    with (output / "validation_summary.json").open(encoding="utf-8") as summary_file:
        summary = json.load(summary_file)
    assert len(rows) == len(jsonl_rows) == report.issue_count
    assert summary == report.as_dict()
    assert set(report.counts_by_severity) <= {"info", "warning", "error", "critical"}
