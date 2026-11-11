import csv
from datetime import datetime
from decimal import Decimal
import hashlib
import math
import json
from pathlib import Path
from typing import Any, Protocol

from bson.decimal128 import Decimal128
from pymongo.database import Database

from backend.app.db.schema import (
    COLLECTION_NAMES,
    INDEXES,
    REQUIRED_FIELDS,
    SCHEMAS,
)
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
        self.lifecycle_events = MongoRepository(database["lifecycle_events"])

    def _repository(self, collection_name: str) -> MongoRepository:
        if collection_name == "ground_truth_labels":
            return self.evaluation.ground_truth_labels
        if collection_name == "evaluation_results":
            return self.evaluation.evaluation_results
        if collection_name == "anomaly_fixtures":
            return self.validation.anomaly_fixtures
        if collection_name == "lifecycle_events":
            return self.lifecycle_events
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


SQL_INSERT_ORDER = (
    "categories",
    "customers",
    "products",
    "sessions",
    "page_views",
    "carts",
    "cart_lines",
    "orders",
    "order_lines",
    "product_relations",
    "lifecycle_events",
    "dataset_splits",
    "ground_truth_labels",
    "anomaly_fixtures",
    "generation_runs",
    "validation_issues",
    "recommendations",
    "model_runs",
    "evaluation_results",
)

SQL_FOREIGN_KEYS = {
    "categories": (("parent_category_id", "categories", "_id"),),
    "products": (("category_id", "categories", "_id"),),
    "sessions": (("customer_id", "customers", "_id"),),
    "page_views": (
        ("session_id", "sessions", "_id"),
        ("customer_id", "customers", "_id"),
        ("product_id", "products", "_id"),
    ),
    "carts": (
        ("customer_id", "customers", "_id"),
        ("session_id", "sessions", "_id"),
    ),
    "cart_lines": (
        ("cart_id", "carts", "_id"),
        ("product_id", "products", "_id"),
    ),
    "orders": (
        ("customer_id", "customers", "_id"),
        ("session_id", "sessions", "_id"),
        ("cart_id", "carts", "_id"),
    ),
    "order_lines": (
        ("order_id", "orders", "_id"),
        ("product_id", "products", "_id"),
    ),
    "product_relations": (
        ("source_product_id", "products", "_id"),
        ("target_product_id", "products", "_id"),
    ),
    "recommendations": (
        ("customer_id", "customers", "_id"),
        ("model_run_id", "model_runs", "_id"),
    ),
    "validation_issues": (("generation_run_id", "generation_runs", "_id"),),
    "anomaly_fixtures": (("generation_run_id", "generation_runs", "_id"),),
    "ground_truth_labels": (
        ("customer_id", "customers", "_id"),
        ("product_id", "products", "_id"),
        ("source_event_id", "order_lines", "_id"),
        ("dataset_split_id", "dataset_splits", "_id"),
    ),
    "model_runs": (("training_split_id", "dataset_splits", "_id"),),
    "evaluation_results": (
        ("model_run_id", "model_runs", "_id"),
        ("dataset_split_id", "dataset_splits", "_id"),
    ),
}


def _sql_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _sql_type(field_schema: dict[str, Any]) -> str:
    bson_type = field_schema["bsonType"]
    if isinstance(bson_type, list):
        bson_type = next(kind for kind in bson_type if kind != "null")
    return {
        "string": "TEXT",
        "date": "TEXT",
        "decimal": "TEXT",
        "int": "INTEGER",
        "long": "INTEGER",
        "double": "REAL",
        "bool": "INTEGER",
        "object": "TEXT",
        "array": "TEXT",
    }[bson_type]


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (Decimal128, Decimal)):
        value = str(value.to_decimal() if isinstance(value, Decimal128) else value)
    if isinstance(value, datetime):
        value = value.isoformat()
    if isinstance(value, dict) or isinstance(value, (list, tuple)):
        value = json.dumps(
            _json_value(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("SQL seed exports require finite floating-point values.")
        return repr(value)
    raise TypeError(f"Unsupported SQL seed value type: {type(value).__name__}.")


def _sql_create_table(collection_name: str) -> str:
    properties = SCHEMAS[collection_name]
    required = set(REQUIRED_FIELDS[collection_name])
    columns = []
    for field_name, field_schema in properties.items():
        column = f"{_sql_identifier(field_name)} {_sql_type(field_schema)}"
        if field_name == "_id":
            column += " PRIMARY KEY"
        elif field_name in required and not (
            isinstance(field_schema["bsonType"], list)
            and "null" in field_schema["bsonType"]
        ):
            column += " NOT NULL"
        columns.append(column)
    for field_name, target_table, target_field in SQL_FOREIGN_KEYS.get(
        collection_name, ()
    ):
        columns.append(
            "FOREIGN KEY "
            f"({_sql_identifier(field_name)}) REFERENCES "
            f"{_sql_identifier(target_table)} ({_sql_identifier(target_field)}) "
            "DEFERRABLE INITIALLY DEFERRED"
        )
    for index in INDEXES[collection_name]:
        if index.get("unique"):
            fields = ", ".join(
                _sql_identifier(field_name)
                for field_name, _ in index["keys"]
            )
            columns.append(f"UNIQUE ({fields})")
    return (
        f"CREATE TABLE {_sql_identifier(collection_name)} "
        f"({', '.join(columns)});"
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ExportGenerationTarget:
    """Stream CSV, JSON, JSONL, and relational SQL seed exports."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        expected_names = [
            "manifest.json",
            "seed_data.sql",
            *(
                f"{collection_name}.{extension}"
                for collection_name in COLLECTION_NAMES
                for extension in ("csv", "jsonl", "json")
            ),
        ]
        existing = [name for name in expected_names if (output_dir / name).exists()]
        if existing:
            raise FileExistsError(
                "Refusing to overwrite existing export files: "
                + ", ".join(existing[:3])
                + (" and more." if len(existing) > 3 else ".")
            )
        self._json_files: dict[str, Any] = {}
        self._json_array_files: dict[str, Any] = {}
        self._json_first_record: dict[str, bool] = {}
        self._csv_files: dict[str, Any] = {}
        self._csv_writers: dict[str, csv.DictWriter] = {}
        self._row_counts = {name: 0 for name in COLLECTION_NAMES}
        self._sql_file = (output_dir / "seed_data.sql").open(
            "w", encoding="utf-8", newline="\n"
        )
        self._sql_file.write(
            "-- Relational SQL export; MongoDB remains the system of record.\n"
            "PRAGMA foreign_keys = ON;\n"
            "PRAGMA defer_foreign_keys = ON;\n"
            "BEGIN TRANSACTION;\n"
        )
        for collection_name in SQL_INSERT_ORDER:
            self._sql_file.write(_sql_create_table(collection_name) + "\n")
        for collection_name in COLLECTION_NAMES:
            fields = list(SCHEMAS[collection_name])
            json_file = (output_dir / f"{collection_name}.jsonl").open(
                "w", encoding="utf-8", newline="\n"
            )
            csv_file = (output_dir / f"{collection_name}.csv").open(
                "w", encoding="utf-8", newline=""
            )
            json_array_file = (output_dir / f"{collection_name}.json").open(
                "w", encoding="utf-8", newline="\n"
            )
            json_array_file.write("[")
            writer = csv.DictWriter(
                csv_file,
                fieldnames=fields,
                extrasaction="raise",
                lineterminator="\n",
            )
            writer.writeheader()
            self._json_files[collection_name] = json_file
            self._json_array_files[collection_name] = json_array_file
            self._json_first_record[collection_name] = True
            self._csv_files[collection_name] = csv_file
            self._csv_writers[collection_name] = writer

    def write_batch(
        self, collection_name: str, documents: list[dict[str, Any]]
    ) -> None:
        for document in documents:
            fields = list(SCHEMAS[collection_name])
            normalized = _json_value(document)
            self._json_files[collection_name].write(
                canonical_json(document) + "\n"
            )
            array_file = self._json_array_files[collection_name]
            if not self._json_first_record[collection_name]:
                array_file.write(",")
            array_file.write(
                json.dumps(
                    normalized,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            self._json_first_record[collection_name] = False
            csv_row: dict[str, Any] = {}
            for field in fields:
                value = document.get(field)
                if value is None:
                    csv_row[field] = ""
                elif isinstance(value, (dict, list, tuple)):
                    csv_row[field] = canonical_json(value)
                else:
                    csv_row[field] = _json_value(value)
            self._csv_writers[collection_name].writerow(csv_row)
            self._row_counts[collection_name] += 1
            sql_columns = ", ".join(_sql_identifier(field) for field in fields)
            sql_values = ", ".join(
                _sql_literal(document.get(field)) for field in fields
            )
            self._sql_file.write(
                f"INSERT INTO {_sql_identifier(collection_name)} "
                f"({sql_columns}) VALUES ({sql_values});\n"
            )

    def finalize(self, manifest: dict[str, Any]) -> None:
        for collection_name, file in self._json_array_files.items():
            file.write("]\n")
        self._sql_file.write("COMMIT;\n")
        for file in (
            *self._json_files.values(),
            *self._json_array_files.values(),
            *self._csv_files.values(),
            self._sql_file,
        ):
            file.flush()
        output_files = []
        for collection_name in COLLECTION_NAMES:
            for extension, format_name in (
                ("csv", "csv"),
                ("jsonl", "jsonl"),
                ("json", "json"),
            ):
                path = self.output_dir / f"{collection_name}.{extension}"
                output_files.append(
                    {
                        "file_name": path.name,
                        "format": format_name,
                        "row_count": self._row_counts[collection_name],
                        "sha256": _file_sha256(path),
                    }
                )
        sql_path = self.output_dir / "seed_data.sql"
        output_files.append(
            {
                "file_name": sql_path.name,
                "format": "sql",
                "row_count": sum(self._row_counts.values()),
                "sha256": _file_sha256(sql_path),
            }
        )
        manifest["exports"] = {
            "files": output_files,
            "manifest_checksum_note": (
                "Checksums cover every collection export and seed_data.sql; "
                "manifest.json is excluded because it contains these checksums."
            ),
        }
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
        for file in (
            *self._json_files.values(),
            *self._json_array_files.values(),
            *self._csv_files.values(),
            self._sql_file,
        ):
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
