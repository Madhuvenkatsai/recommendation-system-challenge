from pymongo import MongoClient
from pymongo.database import Database

from backend.app.core.config import MongoSettings
from backend.app.db.schema import COLLECTION_NAMES

_client: MongoClient | None = None


class NamespacedDatabase:
    """Expose a collection namespace while retaining the same MongoDB database."""

    def __init__(self, database: Database, prefix: str) -> None:
        self._database = database
        self._prefix = prefix

    def __getitem__(self, name: str):
        mapped = f"{self._prefix}{name}" if name in COLLECTION_NAMES else name
        return self._database[mapped]

    def list_collections(self, *args, **kwargs):
        for item in self._database.list_collections(*args, **kwargs):
            name = item["name"]
            if name.startswith(self._prefix) and name[len(self._prefix):] in COLLECTION_NAMES:
                item["name"] = name[len(self._prefix):]
                yield item

    def list_collection_names(self, *args, **kwargs) -> list[str]:
        return [item["name"] for item in self.list_collections(*args, **kwargs)]

    def create_collection(self, name: str, *args, **kwargs):
        mapped = f"{self._prefix}{name}" if name in COLLECTION_NAMES else name
        return self._database.create_collection(mapped, *args, **kwargs)

    def command(self, name, *args, **kwargs):
        if name == "collMod" and args and args[0] in COLLECTION_NAMES:
            args = (f"{self._prefix}{args[0]}", *args[1:])
        return self._database.command(name, *args, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self._database, name)


def get_database(
    *, collection_prefix: str | None = None
) -> Database | NamespacedDatabase:
    global _client

    settings = MongoSettings.from_environment()
    if _client is None:
        _client = MongoClient(
            settings.uri,
            serverSelectionTimeoutMS=10_000,
            tz_aware=True,
        )
    database = _client[settings.database_name]
    prefix = (
        settings.collection_prefix
        if collection_prefix is None
        else collection_prefix
    )
    if prefix == settings.collection_prefix:
        return database if not prefix else NamespacedDatabase(database, prefix)
    if prefix and not prefix.endswith("_"):
        raise ValueError("Collection namespace must end in an underscore.")
    return database if not prefix else NamespacedDatabase(database, prefix)


def close_mongo_connection() -> None:
    global _client

    if _client is not None:
        _client.close()
        _client = None
