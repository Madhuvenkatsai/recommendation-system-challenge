import re
from copy import deepcopy

import anyio
import httpx
import pytest

from backend.app.api.routes.catalog import get_catalog_database
from backend.app.api.routes.dashboard import get_dashboard_database
from backend.app.main import app


class Cursor:
    def __init__(self, documents):
        self.documents = list(documents)

    def sort(self, fields):
        for field, direction in reversed(fields):
            self.documents.sort(
                key=lambda row: row.get(field) or "",
                reverse=direction < 0,
            )
        return self

    def skip(self, count):
        self.documents = self.documents[count:]
        return self

    def limit(self, count):
        self.documents = self.documents[:count]
        return self

    def __iter__(self):
        return iter(self.documents)


def _matches(document, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches(document, option) for option in expected):
                return False
            continue
        actual = document.get(key)
        if isinstance(expected, dict) and "$regex" in expected:
            if not re.search(expected["$regex"], str(actual or ""), re.I):
                return False
        elif isinstance(expected, dict) and "$in" in expected:
            if actual not in expected["$in"]:
                return False
        elif actual != expected:
            return False
    return True


class Collection:
    def __init__(self, documents=()):
        self.documents = [deepcopy(row) for row in documents]

    def find_one(self, query=None, projection=None, *, sort=None):
        rows = list(self.find(query, projection))
        if sort:
            rows = list(Cursor(rows).sort(sort))
        return rows[0] if rows else None

    def find(self, query=None, projection=None):
        rows = [
            deepcopy(row)
            for row in self.documents
            if _matches(row, query or {})
        ]
        if projection and any(value for value in projection.values()):
            included = {key for key, value in projection.items() if value}
            rows = [
                {key: value for key, value in row.items() if key in included}
                for row in rows
            ]
        return Cursor(rows)

    def count_documents(self, query):
        return sum(_matches(row, query) for row in self.documents)

    def aggregate(self, pipeline):
        query = pipeline[0]["$match"]
        rows = [row for row in self.documents if _matches(row, query)]
        counts = {}
        for row in rows:
            key = (row["severity"], row["issue_type"])
            counts[key] = counts.get(key, 0) + 1
        return [
            {
                "_id": {"severity": key[0], "issue_type": key[1]},
                "count": value,
            }
            for key, value in counts.items()
        ]


class Database:
    name = "test_recommendations"

    def __init__(self, collections):
        self.collections = {
            name: Collection(rows) for name, rows in collections.items()
        }

    def __getitem__(self, name):
        return self.collections.setdefault(name, Collection())

    def command(self, name):
        assert name == "ping"
        return {"ok": 1}


async def call(method, path, payload=None, headers=None):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        return await client.request(method, path, json=payload, headers=headers)


@pytest.fixture(autouse=True)
def clear_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_dashboard_overview_returns_actual_counts_and_validation_data():
    run = {
        "_id": "RUN_DASHBOARD_TEST",
        "status": "completed",
        "seed": 20261022,
        "started_at": "2025-01-01",
        "completed_at": "2025-01-02",
        "configuration": {"customers": 2, "products": 1},
        "collection_counts": {"customers": 2, "products": 1, "sessions": 3, "orders": 1},
    }
    issue = {
        "_id": "ISS_TEST",
        "issue_id": "ISS_TEST",
        "generation_run_id": run["_id"],
        "severity": "warning",
        "issue_type": "test_issue",
    }
    database = Database(
        {
            "generation_runs": [run],
            "customers": [{"_id": "CUS1"}, {"_id": "CUS2"}],
            "products": [{"_id": "PRO1"}],
            "sessions": [{"_id": "SES1"}, {"_id": "SES2"}, {"_id": "SES3"}],
            "orders": [{"_id": "ORD1"}],
            "validation_issues": [issue],
        }
    )
    app.dependency_overrides[get_dashboard_database] = lambda: database

    response = anyio.run(call, "GET", "/api/v1/dashboard/overview")

    assert response.status_code == 200
    body = response.json()
    assert body["database"]["status"] == "connected"
    assert body["counts"] == {
        "customers": 2,
        "products": 1,
        "sessions": 3,
        "orders": 1,
    }
    assert body["generation"]["latest_run"]["_id"] == run["_id"]
    assert body["validation"]["status"] == "completed"
    assert body["validation"]["issue_count"] == 1
    assert body["validation"]["counts_by_severity"] == {"warning": 1}
    assert body["recommendations"]["ground_truth_labels_are_model_inputs"] is False


def test_catalog_search_filters_and_paginates_real_database_records():
    database = Database(
        {
            "products": [
                {
                    "_id": "PRO1",
                    "name": "Trail Pack",
                    "brand": "North",
                    "category_id": "CAT1",
                    "status": "active",
                    "price": 25,
                    "currency": "USD",
                },
                {
                    "_id": "PRO2",
                    "name": "Desk Lamp",
                    "brand": "Home",
                    "category_id": "CAT2",
                    "status": "discontinued",
                    "price": 40,
                    "currency": "USD",
                },
            ],
            "categories": [
                {"_id": "CAT1", "name": "Outdoor"},
                {"_id": "CAT2", "name": "Home"},
            ],
        }
    )
    app.dependency_overrides[get_catalog_database] = lambda: database

    response = anyio.run(
        call,
        "GET",
        "/api/v1/catalog/products?search=trail&status=active&limit=1",
    )

    assert response.status_code == 200
    result = response.json()
    assert result["total"] == 1
    assert result["items"][0]["_id"] == "PRO1"
    assert result["items"][0]["category"]["name"] == "Outdoor"


def test_generation_refuses_to_overwrite_existing_dataset_records():
    database = Database({"customers": [{"_id": "CUS_EXISTING"}]})
    app.dependency_overrides[get_dashboard_database] = lambda: database

    response = anyio.run(
        call,
        "POST",
        "/api/v1/generation",
        {"scale": "starter", "seed": 20261022},
    )

    assert response.status_code == 409
    assert "will not overwrite" in response.json()["detail"]


def test_generation_configuration_is_served_from_backend_values():
    response = anyio.run(call, "GET", "/api/v1/generation/configurations")

    assert response.status_code == 200
    result = response.json()
    assert result["seed"] == 20261022
    scales = {item["value"]: item["configuration"] for item in result["scales"]}
    assert scales["starter"]["customers"] == 200
    assert scales["starter"]["sessions"] == 2_500
    assert scales["full"]["customers"] == 20_000
    assert scales["full"]["orders"] == 100_000


def test_clean_completed_validation_summary_is_not_reported_as_not_run():
    generation_run = {
        "_id": "RUN_CLEAN_VALIDATION",
        "status": "completed",
        "validation_summary": {
            "validation_run_id": "VAL_CLEAN",
            "generation_run_id": "RUN_CLEAN_VALIDATION",
            "issue_count": 0,
            "counts_by_issue_type": {},
            "counts_by_severity": {},
            "clean_record_count": 12,
            "anomalous_record_count": 0,
        },
    }
    database = Database({"generation_runs": [generation_run]})
    app.dependency_overrides[get_dashboard_database] = lambda: database

    response = anyio.run(call, "GET", "/api/v1/validation/summary")

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "completed"
    assert result["issue_count"] == 0
    assert result["clean_record_count"] == 12


def test_local_development_cors_allows_vite_origin_and_blocks_unknown_origin():
    allowed = anyio.run(
        call,
        "OPTIONS",
        "/api/v1/health",
        None,
        {
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    blocked = anyio.run(
        call,
        "OPTIONS",
        "/api/v1/health",
        None,
        {
            "Origin": "http://example.invalid",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-origin" not in blocked.headers
