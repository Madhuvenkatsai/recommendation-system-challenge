from pymongo import MongoClient
from pymongo.database import Database

from backend.app.core.config import MongoSettings

_client: MongoClient | None = None


def get_database() -> Database:
    global _client

    settings = MongoSettings.from_environment()
    if _client is None:
        _client = MongoClient(settings.uri, serverSelectionTimeoutMS=2000)
    return _client[settings.database_name]


def close_mongo_connection() -> None:
    global _client

    if _client is not None:
        _client.close()
        _client = None
