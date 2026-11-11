import csv
import json
from pathlib import Path
from typing import Any

from pymongo.database import Database

from backend.app.repositories.validation import get_validation_repositories
from backend.app.validation.engine import ISSUE_FIELDS


class ValidationExportTarget:
    def __init__(self, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        self._jsonl = (output_dir / "validation_issues.jsonl").open(
            "w", encoding="utf-8", newline="\n"
        )
        self._csv_file = (output_dir / "validation_issues.csv").open(
            "w", encoding="utf-8", newline=""
        )
        self._csv = csv.DictWriter(
            self._csv_file,
            fieldnames=ISSUE_FIELDS,
            lineterminator="\n",
        )
        self._csv.writeheader()
        self._output_dir = output_dir

    def write_batch(self, documents: list[dict[str, Any]]) -> None:
        for document in documents:
            row = {
                field: document[field]
                for field in ISSUE_FIELDS
            }
            self._jsonl.write(
                json.dumps(
                    document,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=_json_value,
                )
                + "\n"
            )
            csv_row = dict(row)
            csv_row["source_record_ids"] = json.dumps(
                row["source_record_ids"], separators=(",", ":")
            )
            csv_row["detected_at"] = row["detected_at"].isoformat()
            self._csv.writerow(csv_row)

    def finalize(self, report: dict[str, Any]) -> None:
        with (self._output_dir / "validation_summary.json").open(
            "w", encoding="utf-8", newline="\n"
        ) as summary:
            json.dump(report, summary, sort_keys=True, indent=2)
            summary.write("\n")

    def close(self) -> None:
        self._jsonl.close()
        self._csv_file.close()


class ValidationMongoTarget:
    def __init__(self, database: Database) -> None:
        self._issues = get_validation_repositories(database).validation_issues

    def write_batch(self, documents: list[dict[str, Any]]) -> None:
        self._issues.upsert_many_by_id(documents)

    def finalize(self, report: dict[str, Any]) -> None:
        return None

    def close(self) -> None:
        return None


class CompositeValidationTarget:
    def __init__(self, *targets: Any) -> None:
        self._targets = targets

    def write_batch(self, documents: list[dict[str, Any]]) -> None:
        for target in self._targets:
            target.write_batch(documents)

    def finalize(self, report: dict[str, Any]) -> None:
        for target in self._targets:
            target.finalize(report)

    def close(self) -> None:
        for target in self._targets:
            target.close()


def _json_value(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "to_decimal"):
        return str(value.to_decimal())
    return str(value)
