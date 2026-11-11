import csv
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any, Protocol

from bson.decimal128 import Decimal128
from pymongo.database import Database

from backend.app.db.schema import COLLECTION_NAMES, SCHEMAS
from backend.app.repositories.evaluation import get_evaluation_repositories
from backend.app.repositories.model_input import get_model_input_repositories
from backend.app.repositories.mongo import MongoRepository
from backend.app.repositories.validation import get_validation_repositories


class GenerationTarget(Protocol):
    def write_batch(
        self, collection_name: str, documents: list[dict[str, Any]]
    ) -> None: ...

    def finalize(self, manifest: dict[str, Any]) -> None: ...

    def close(self) -> None: ...


class MongoGenerationTarget:
    """Write bounded batches through the existing Mongo repository bundles."""

    def __init__(self, database: Database) -> None:
        self.model_input = get_model_input_repositories(database)
        self.evaluation = get_evaluation_repositories(database)
        self.validation = get_validation_repositories(database)

    def _repository(self, collection_name: str) -> MongoRepository:
        if collection_name == "ground_truth_labels":
            return self.evaluation.ground_truth_labels
        if collection_name == "evaluation_results":
            return self.evaluation.evaluation_results
        if collection_name == "anomaly_fixtures":
            return self.validation.anomaly_fixtures
        return getattr(self.model_input, collection_name)

    def write_batch(
        self, collection_name: str, documents: list[dict[str, Any]]
    ) -> None:
        self._repository(collection_name).insert_many(documents)

    def finalize(self, manifest: dict[str, Any]) -> None:
        return None

    def close(self) -> None:
        return None


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal128):
        return str(value.to_decimal())
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_value(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(nested) for nested in value]
    return value


def canonical_json(document: dict[str, Any]) -> str:
    return json.dumps(
        _json_value(document),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


class ExportGenerationTarget:
    """Stream per-collection CSV and JSON Lines files and a final manifest."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._json_files: dict[str, Any] = {}
        self._csv_files: dict[str, Any] = {}
        self._csv_writers: dict[str, csv.DictWriter] = {}
        for collection_name in COLLECTION_NAMES:
            fields = list(SCHEMAS[collection_name])
            json_file = (output_dir / f"{collection_name}.jsonl").open(
                "w", encoding="utf-8", newline="\n"
            )
            csv_file = (output_dir / f"{collection_name}.csv").open(
                "w", encoding="utf-8", newline=""
            )
            writer = csv.DictWriter(
                csv_file,
                fieldnames=fields,
                extrasaction="raise",
                lineterminator="\n",
            )
            writer.writeheader()
            self._json_files[collection_name] = json_file
            self._csv_files[collection_name] = csv_file
            self._csv_writers[collection_name] = writer

    def write_batch(
        self, collection_name: str, documents: list[dict[str, Any]]
    ) -> None:
        for document in documents:
            self._json_files[collection_name].write(
                canonical_json(document) + "\n"
            )
            csv_row: dict[str, Any] = {}
            for field in SCHEMAS[collection_name]:
                value = document.get(field)
                if value is None:
                    csv_row[field] = ""
                elif isinstance(value, (dict, list, tuple)):
                    csv_row[field] = canonical_json({"value": value})
                else:
                    csv_row[field] = _json_value(value)
            self._csv_writers[collection_name].writerow(csv_row)

    def finalize(self, manifest: dict[str, Any]) -> None:
        path = self.output_dir / "manifest.json"
        with path.open("w", encoding="utf-8", newline="\n") as manifest_file:
            json.dump(
                manifest,
                manifest_file,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            manifest_file.write("\n")

    def close(self) -> None:
        for file in (*self._json_files.values(), *self._csv_files.values()):
            file.close()


class CompositeGenerationTarget:
    def __init__(self, *targets: GenerationTarget) -> None:
        self.targets = targets

    def write_batch(
        self, collection_name: str, documents: list[dict[str, Any]]
    ) -> None:
        for target in self.targets:
            target.write_batch(collection_name, documents)

    def finalize(self, manifest: dict[str, Any]) -> None:
        for target in self.targets:
            target.finalize(manifest)

    def close(self) -> None:
        for target in self.targets:
            target.close()


def empty_checksum() -> str:
    return hashlib.sha256().hexdigest()
