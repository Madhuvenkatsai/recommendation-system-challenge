import os
from dataclasses import dataclass


class MongoConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class MongoSettings:
    uri: str
    database_name: str

    @classmethod
    def from_environment(cls) -> "MongoSettings":
        uri = os.environ.get("MONGODB_URI", "").strip()
        if not uri:
            raise MongoConfigurationError(
                "MongoDB is not configured. Set the MONGODB_URI environment variable."
            )

        database_name = os.environ.get(
            "MONGODB_DATABASE", "product_recommendations"
        ).strip()
        if not database_name:
            raise MongoConfigurationError(
                "MongoDB is not configured. MONGODB_DATABASE must not be empty."
            )

        return cls(uri=uri, database_name=database_name)
