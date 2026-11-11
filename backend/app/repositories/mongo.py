from collections.abc import Iterable, Mapping
from typing import Any

from pymongo.collection import Collection
from pymongo import ReplaceOne
from pymongo.results import (
    DeleteResult,
    InsertManyResult,
    InsertOneResult,
    UpdateResult,
)


class MongoRepository:
    """Small collection-bound CRUD surface; MongoDB validators enforce shape."""

    def __init__(self, collection: Collection[Any]) -> None:
        self.collection = collection

    def insert_one(self, document: Mapping[str, Any]) -> InsertOneResult:
        document_id = document.get("_id")
        if not isinstance(document_id, str) or not document_id.strip():
            raise ValueError("Documents require a non-empty string _id.")
        return self.collection.insert_one(dict(document))

    def insert_many(
        self, documents: list[Mapping[str, Any]]
    ) -> InsertManyResult | None:
        if not documents:
            return None
        prepared = [dict(document) for document in documents]
        if any(
            not isinstance(document.get("_id"), str)
            or not document["_id"].strip()
            for document in prepared
        ):
            raise ValueError("Every document requires a non-empty string _id.")
        return self.collection.insert_many(prepared, ordered=True)

    def get_by_id(self, document_id: str) -> dict[str, Any] | None:
        return self.collection.find_one({"_id": document_id})

    def find_many(
        self,
        query: Mapping[str, Any] | None = None,
        *,
        limit: int = 100,
        projection: Mapping[str, int] | None = None,
    ) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit must be greater than zero.")
        cursor = self.collection.find(dict(query or {}), projection)
        return list(cursor.limit(limit))

    def iter_many(
        self,
        query: Mapping[str, Any] | None = None,
        *,
        projection: Mapping[str, int] | None = None,
        batch_size: int = 1_000,
        sort: list[tuple[str, int]] | None = None,
    ) -> Iterable[dict[str, Any]]:
        if batch_size < 1:
            raise ValueError("batch_size must be greater than zero.")
        cursor = self.collection.find(dict(query or {}), projection)
        if sort:
            cursor = cursor.sort(sort)
        return cursor.batch_size(batch_size)

    def iter_aggregate(
        self,
        pipeline: list[Mapping[str, Any]],
        *,
        batch_size: int = 1_000,
    ) -> Iterable[dict[str, Any]]:
        if batch_size < 1:
            raise ValueError("batch_size must be greater than zero.")
        return self.collection.aggregate(
            [dict(stage) for stage in pipeline], allowDiskUse=True
        ).batch_size(batch_size)

    def upsert_by_id(self, document: Mapping[str, Any]) -> UpdateResult:
        document_id = document.get("_id")
        if not isinstance(document_id, str) or not document_id.strip():
            raise ValueError("Documents require a non-empty string _id.")
        return self.collection.replace_one(
            {"_id": document_id}, dict(document), upsert=True
        )

    def upsert_many_by_id(
        self, documents: list[Mapping[str, Any]]
    ) -> int:
        if not documents:
            return 0
        operations = []
        for document in documents:
            document_id = document.get("_id")
            if not isinstance(document_id, str) or not document_id.strip():
                raise ValueError("Documents require a non-empty string _id.")
            operations.append(
                ReplaceOne({"_id": document_id}, dict(document), upsert=True)
            )
        result = self.collection.bulk_write(operations, ordered=True)
        return result.upserted_count + result.modified_count

    def update_by_id(
        self, document_id: str, updates: Mapping[str, Any]
    ) -> UpdateResult:
        if not updates:
            raise ValueError("updates must not be empty.")
        if "_id" in updates:
            raise ValueError("_id cannot be changed.")
        return self.collection.update_one(
            {"_id": document_id}, {"$set": dict(updates)}
        )

    def delete_by_id(self, document_id: str) -> DeleteResult:
        return self.collection.delete_one({"_id": document_id})
