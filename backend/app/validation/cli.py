import argparse
from pathlib import Path
from typing import Any

from backend.app.db.initialize import initialize_database
from backend.app.db.mongo import get_database
from backend.app.db.schema import COLLECTION_NAMES
from backend.app.validation.engine import ValidationEngine
from backend.app.validation.targets import (
    CompositeValidationTarget,
    ValidationExportTarget,
    ValidationMongoTarget,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate generated e-commerce data and detect anomalies."
    )
    parser.add_argument(
        "--generation-run-id",
        help="Run to validate; defaults to the latest completed generation run.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("validation-output"),
        help="Directory for issue CSV/JSONL and validation summary exports.",
    )
    parser.add_argument("--batch-size", type=int, default=1_000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    database = get_database()
    initialize_database(database)
    generation_run_id = args.generation_run_id
    if generation_run_id is None:
        latest = database["generation_runs"].find_one(
            {"status": "completed"},
            sort=[("completed_at", -1)],
            projection={"_id": 1},
        )
        if latest is None:
            raise RuntimeError("No completed generation run exists in MongoDB.")
        generation_run_id = latest["_id"]

    sources: dict[str, Any] = {
        name: (lambda collection=name: database[collection].find({}))
        for name in COLLECTION_NAMES
        if name != "validation_issues"
    }
    target = CompositeValidationTarget(
        ValidationMongoTarget(database),
        ValidationExportTarget(args.output_dir),
    )
    report = ValidationEngine(batch_size=args.batch_size).run(
        sources,
        generation_run_id=generation_run_id,
        target=target,
    )
    print(
        f"Validation {report.validation_run_id}: {report.issue_count} issues "
        f"across {report.clean_record_count} clean and "
        f"{report.anomalous_record_count} fixture records."
    )
    print(f"Issue exports and summary: {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
