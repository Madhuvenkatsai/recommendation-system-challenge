from backend.app.db.initialize import initialize_database
from backend.app.db.schema import (
    COLLECTION_NAMES,
    CORE_COLLECTIONS,
    INDEXES,
    REQUIRED_FIELDS,
    SCHEMAS,
    SUPPORTING_COLLECTIONS,
    validator_for,
)
from backend.app.repositories.evaluation import get_evaluation_repositories
from backend.app.repositories.model_input import get_model_input_repositories


class FakeCollection:
    def __init__(self) -> None:
        self.indexes: list[tuple[list[tuple[str, int]], dict[str, object]]] = []

    def create_index(self, keys, **options) -> str:
        self.indexes.append((keys, options))
        return str(options["name"])


class FakeDatabase:
    def __init__(
        self,
        existing: tuple[str, ...] = (),
        validators: dict[str, dict[str, object]] | None = None,
    ) -> None:
        self.collections = {name: FakeCollection() for name in existing}
        self.collection_options = {
            name: {"validator": validator}
            for name, validator in (validators or {}).items()
        }
        self.commands: list[tuple[str, dict[str, object]]] = []

    def list_collection_names(self) -> list[str]:
        return list(self.collections)

    def list_collections(self) -> list[dict[str, object]]:
        return [
            {"name": name, "options": self.collection_options.get(name, {})}
            for name in self.collections
        ]

    def create_collection(self, name: str, **options) -> FakeCollection:
        self.commands.append(("create_collection", {"name": name, **options}))
        self.collections[name] = FakeCollection()
        self.collection_options[name] = options
        return self.collections[name]

    def command(self, name: str, collection: str, **options) -> dict[str, str]:
        self.commands.append((name, {"collection": collection, **options}))
        if name == "collMod":
            self.collection_options[collection] = options
        return {"ok": "1"}

    def __getitem__(self, name: str) -> FakeCollection:
        return self.collections[name]


def test_schema_and_indexes_cover_all_required_collections() -> None:
    assert len(CORE_COLLECTIONS) == 11
    assert len(SUPPORTING_COLLECTIONS) == 8
    assert len(COLLECTION_NAMES) == 19
    assert set(SCHEMAS) == set(COLLECTION_NAMES)
    assert set(REQUIRED_FIELDS) == set(COLLECTION_NAMES)
    assert set(INDEXES) == set(COLLECTION_NAMES)
    assert set(REQUIRED_FIELDS["validation_issues"]) == {
        "_id",
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
    }
    assert "fixture_records" in REQUIRED_FIELDS["anomaly_fixtures"]
    assert {
        "entity_type",
        "entity_id",
        "previous_state",
        "new_state",
        "event_type",
        "occurred_at",
        "sequence",
        "source_type",
        "source_id",
    } <= set(REQUIRED_FIELDS["lifecycle_events"])

    for collection_name in COLLECTION_NAMES:
        schema = validator_for(collection_name)["$jsonSchema"]
        assert schema["bsonType"] == "object"
        assert schema["properties"]["_id"]["bsonType"] == "string"
        assert set(schema["required"]) <= set(schema["properties"])
        assert schema["additionalProperties"] is True
        assert all(
            "bsonType" in field_schema
            for field_schema in schema["properties"].values()
        )
        assert INDEXES[collection_name]
        assert all(
            index.get("name")
            and all(field in schema["properties"] for field, _ in index["keys"])
            for index in INDEXES[collection_name]
        )


def test_optional_fields_are_not_required_and_nullable_fields_are_typed() -> None:
    product = validator_for("products")["$jsonSchema"]
    assert "category_id" not in product["required"]
    assert product["properties"]["category_id"]["bsonType"] == ["string", "null"]
    assert product["properties"]["price"]["bsonType"] == "decimal"

    page_view = validator_for("page_views")["$jsonSchema"]
    assert "referrer" not in page_view["required"]
    assert page_view["properties"]["occurred_at"]["bsonType"] == "date"

    recommendation = validator_for("recommendations")["$jsonSchema"]
    assert recommendation["properties"]["strategy"]["enum"] == [
        "popularity",
        "content",
        "hybrid",
    ]
    assert recommendation["properties"]["k"]["bsonType"] == "int"
    assert "ground_truth_labels" not in recommendation["properties"]
    metric = validator_for("evaluation_results")["$jsonSchema"]["properties"][
        "metrics"
    ]["properties"]["precision_at_k"]
    assert "null" in metric["bsonType"]


def test_initialization_creates_collections_validators_and_indexes() -> None:
    db = FakeDatabase()

    report = initialize_database(db)

    assert report.created_collections == COLLECTION_NAMES
    assert report.updated_collections == ()
    assert report.index_count == sum(len(specs) for specs in INDEXES.values())
    assert set(db.collections) == set(COLLECTION_NAMES)
    for collection_name in COLLECTION_NAMES:
        options = next(
            options
            for operation, options in db.commands
            if operation == "create_collection"
            and options["name"] == collection_name
        )
        assert options["validationLevel"] == "strict"
        assert options["validationAction"] == "error"
        assert options["validator"] == validator_for(collection_name)
        assert len(db[collection_name].indexes) == len(INDEXES[collection_name])


def test_initialization_updates_existing_collections_idempotently() -> None:
    db = FakeDatabase(COLLECTION_NAMES)

    report = initialize_database(db)

    assert report.created_collections == ()
    assert report.updated_collections == COLLECTION_NAMES
    assert report.index_count == sum(len(specs) for specs in INDEXES.values())
    assert len([command for command in db.commands if command[0] == "collMod"]) == len(
        COLLECTION_NAMES
    )
    assert all(
        options["validationAction"] == "error"
        for operation, options in db.commands
        if operation == "collMod"
    )


def test_initialization_skips_collmod_for_matching_existing_validators() -> None:
    validators = {
        name: validator_for(name)
        for name in COLLECTION_NAMES
    }
    db = FakeDatabase(COLLECTION_NAMES, validators)

    report = initialize_database(db)

    assert report.created_collections == ()
    assert report.updated_collections == ()
    assert report.index_count == sum(len(specs) for specs in INDEXES.values())
    assert not [command for command in db.commands if command[0] == "collMod"]
    assert all(len(db[name].indexes) == len(INDEXES[name]) for name in COLLECTION_NAMES)


def test_ground_truth_is_not_in_model_input_repository_bundle() -> None:
    db = FakeDatabase(COLLECTION_NAMES)

    model_inputs = get_model_input_repositories(db)
    evaluation = get_evaluation_repositories(db)

    assert not hasattr(model_inputs, "ground_truth_labels")
    assert not hasattr(model_inputs, "validation_issues")
    assert not hasattr(model_inputs, "anomaly_fixtures")
    assert not hasattr(model_inputs, "lifecycle_events")
    assert hasattr(evaluation, "ground_truth_labels")
