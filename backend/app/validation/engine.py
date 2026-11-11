from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping, Protocol

from backend.app.db.schema import CORE_COLLECTIONS
from backend.app.validation.validators import (
    Rows,
    ValidationContext,
    prepare_context,
    validate_anomaly_fixtures,
    validate_cart_and_order_arithmetic,
    validate_category_hierarchy,
    validate_lifecycle_and_availability,
    validate_references,
    validate_session_and_event_chronology,
    validate_split_chronology,
)

ISSUE_FIELDS = (
    "issue_id",
    "issue_type",
    "severity",
    "entity_type",
    "entity_id",
    "source_record_ids",
    "generation_run_id",
    "detected_at",
    "description",
    "ground_truth_label",
)


class ValidationTarget(Protocol):
    def write_batch(self, documents: list[dict[str, Any]]) -> None: ...

    def finalize(self, report: dict[str, Any]) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class ValidationReport:
    validation_run_id: str
    generation_run_id: str
    validated_at: datetime
    issue_count: int
    counts_by_issue_type: dict[str, int]
    counts_by_severity: dict[str, int]
    clean_record_count: int
    anomalous_record_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "validation_run_id": self.validation_run_id,
            "generation_run_id": self.generation_run_id,
            "validated_at": self.validated_at.isoformat(),
            "issue_count": self.issue_count,
            "counts_by_issue_type": self.counts_by_issue_type,
            "counts_by_severity": self.counts_by_severity,
            "clean_record_count": self.clean_record_count,
            "anomalous_record_count": self.anomalous_record_count,
        }


class ValidationEngine:
    def __init__(
        self,
        *,
        batch_size: int = 1_000,
        validated_at: datetime | None = None,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be greater than zero.")
        if validated_at is not None and validated_at.tzinfo is None:
            raise ValueError("validated_at must be timezone-aware.")
        self.batch_size = batch_size
        self.validated_at = validated_at or datetime(2026, 1, 1, tzinfo=timezone.utc)

    def run(
        self,
        sources: Mapping[str, Rows],
        *,
        generation_run_id: str,
        target: ValidationTarget,
    ) -> ValidationReport:
        counts_by_type: Counter[str] = Counter()
        counts_by_severity: Counter[str] = Counter()
        issue_count = 0
        batch: list[dict[str, Any]] = []
        seen_issue_ids: set[str] = set()

        def emit(
            issue_type: str,
            severity: str,
            entity_type: str,
            entity_id: str | None,
            source_record_ids: list[Any],
            description: str,
            ground_truth_label: str,
        ) -> None:
            nonlocal issue_count, batch
            source_ids = sorted(
                {value for value in source_record_ids if isinstance(value, str)}
            )
            identity = json.dumps(
                [
                    generation_run_id,
                    issue_type,
                    entity_type,
                    entity_id,
                    source_ids,
                ],
                separators=(",", ":"),
                ensure_ascii=True,
            )
            issue_id = "ISS" + hashlib.blake2b(
                identity.encode("utf-8"), digest_size=16
            ).hexdigest().upper()
            if issue_id in seen_issue_ids:
                return
            seen_issue_ids.add(issue_id)
            issue = {
                "_id": issue_id,
                "issue_id": issue_id,
                "issue_type": issue_type,
                "severity": severity,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "source_record_ids": source_ids,
                "generation_run_id": generation_run_id,
                "detected_at": self.validated_at,
                "description": description,
                "ground_truth_label": ground_truth_label,
            }
            issue_count += 1
            counts_by_type[issue_type] += 1
            counts_by_severity[severity] += 1
            batch.append(issue)
            if len(batch) >= self.batch_size:
                target.write_batch(batch)
                batch = []

        try:
            context = ValidationContext(
                sources=sources,
                generation_run_id=generation_run_id,
                detected_at=self.validated_at,
                emit=emit,
            )
            prepare_context(context)
            validate_references(context)
            validate_category_hierarchy(context)
            validate_session_and_event_chronology(context)
            validate_cart_and_order_arithmetic(context)
            validate_lifecycle_and_availability(context)
            validate_split_chronology(context)
            validate_anomaly_fixtures(context)
            if batch:
                target.write_batch(batch)
                batch = []

            clean_count = sum(context.counts.get(name, 0) for name in CORE_COLLECTIONS)
            anomaly_count = sum(
                len(fixture.get("fixture_records", ()))
                for fixture in context.rows("anomaly_fixtures")
            )
            fingerprint = hashlib.blake2b(
                generation_run_id.encode("utf-8"), digest_size=8
            ).hexdigest().upper()
            report = ValidationReport(
                validation_run_id=f"VAL{fingerprint}",
                generation_run_id=generation_run_id,
                validated_at=self.validated_at,
                issue_count=issue_count,
                counts_by_issue_type=dict(sorted(counts_by_type.items())),
                counts_by_severity=dict(sorted(counts_by_severity.items())),
                clean_record_count=clean_count,
                anomalous_record_count=anomaly_count,
            )
            target.finalize(report.as_dict())
            return report
        finally:
            target.close()
