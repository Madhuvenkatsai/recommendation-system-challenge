import logging
from dataclasses import dataclass
from typing import Any

from pymongo.database import Database

from backend.app.db.mongo import get_database
from backend.app.db.schema import COLLECTION_NAMES, INDEXES, validator_for

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InitializationReport:
    created_collections: tuple[str, ...]
    updated_collections: tuple[str, ...]
    index_count: int


def initialize_database(database: Any | None = None) -> InitializationReport:
    """Create or update MongoDB validators and indexes without inserting data."""
    db = database if database is not None else get_database()
    existing = set(db.list_collection_names())
    created: list[str] = []
    updated: list[str] = []
    index_count = 0

    for collection_name in COLLECTION_NAMES:
        validator = validator_for(collection_name)
        if collection_name in existing:
            db.command(
                "collMod",
                collection_name,
                validator=validator,
                validationLevel="strict",
                validationAction="error",
            )
            updated.append(collection_name)
        else:
            db.create_collection(
                collection_name,
                validator=validator,
                validationLevel="strict",
                validationAction="error",
            )
            created.append(collection_name)

        collection = db[collection_name]
        for index in INDEXES[collection_name]:
            options = {
                key: value
                for key, value in index.items()
                if key not in {"keys"}
            }
            collection.create_index(index["keys"], **options)
            index_count += 1

    logger.info(
        "MongoDB schema initialized: %d created, %d updated, %d indexes",
        len(created),
        len(updated),
        index_count,
    )
    return InitializationReport(tuple(created), tuple(updated), index_count)


def main() -> None:
    report = initialize_database()
    print(
        "MongoDB schema initialized "
        f"({len(report.created_collections)} collections created, "
        f"{len(report.updated_collections)} updated, "
        f"{report.index_count} indexes ensured)."
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
