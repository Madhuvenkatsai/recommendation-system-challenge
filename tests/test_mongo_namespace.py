from backend.app.db.initialize import initialize_database
from backend.app.db.mongo import NamespacedDatabase
from backend.app.db.schema import COLLECTION_NAMES, INDEXES, validator_for


class FakeCollection:
    def __init__(self) -> None:
        self.indexes: list[dict] = []

    def create_index(self, keys, **options) -> str:
        self.indexes.append({"keys": keys, **options})
        return options["name"]


class FakeDatabase:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}
        self.options: dict[str, dict] = {}
        self.commands: list[tuple[str, tuple, dict]] = []

    def __getitem__(self, name: str) -> FakeCollection:
        return self.collections.setdefault(name, FakeCollection())

    def list_collections(self):
        return iter(
            {
                "name": name,
                "options": self.options.get(name, {}),
            }
            for name in self.collections
        )

    def create_collection(self, name: str, **options):
        self.collections[name] = FakeCollection()
        self.options[name] = options
        return self.collections[name]

    def command(self, name, *args, **kwargs):
        self.commands.append((name, args, kwargs))
        return {"ok": 1}


def test_namespace_initialization_only_touches_prefixed_collections() -> None:
    base = FakeDatabase()
    namespace = NamespacedDatabase(base, "full_")

    report = initialize_database(namespace)

    assert report.created_collections == COLLECTION_NAMES
    assert set(base.collections) == {f"full_{name}" for name in COLLECTION_NAMES}
    assert all(
        base.options[f"full_{name}"]["validator"] == validator_for(name)
        for name in COLLECTION_NAMES
    )
    assert all(
        len(base.collections[f"full_{name}"].indexes) == len(INDEXES[name])
        for name in COLLECTION_NAMES
    )


def test_namespace_maps_schema_collection_access_and_collmod() -> None:
    base = FakeDatabase()
    namespace = NamespacedDatabase(base, "full_")

    assert namespace["customers"] is base["full_customers"]
    namespace.command("collMod", "customers", validator={})

    assert base.commands[-1][0] == "collMod"
    assert base.commands[-1][1][0] == "full_customers"
