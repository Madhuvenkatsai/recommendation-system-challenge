from backend.app.db import mongo


class FakeMongoClient:
    def __init__(self, uri: str, **options: object) -> None:
        self.uri = uri
        self.options = options
        self.database_names: list[str] = []

    def __getitem__(self, database_name: str) -> object:
        self.database_names.append(database_name)
        return object()

    def close(self) -> None:
        pass


def test_mongo_client_decodes_utc_timestamps_as_timezone_aware(monkeypatch) -> None:
    fake_client = FakeMongoClient("mongodb://example.invalid")

    def create_client(uri: str, **options: object) -> FakeMongoClient:
        fake_client.uri = uri
        fake_client.options = options
        return fake_client

    monkeypatch.setattr(mongo, "MongoClient", create_client)
    monkeypatch.setattr(mongo, "_client", None)
    monkeypatch.setenv("MONGODB_URI", "mongodb://example.invalid")
    monkeypatch.setenv("MONGODB_DATABASE", "test_database")

    mongo.get_database()

    assert fake_client.options["tz_aware"] is True
    assert fake_client.options["serverSelectionTimeoutMS"] == 10_000
    assert fake_client.database_names == ["test_database"]
    mongo.close_mongo_connection()
