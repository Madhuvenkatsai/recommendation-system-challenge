import anyio
import httpx

from backend.app.api.routes.recommendations import get_recommendation_service
from backend.app.core.config import MongoConfigurationError
from backend.app.main import app


class FakeRecommendationService:
    def generate_for_customer(self, customer_id: str, **kwargs):
        return {
            "_id": "REC_TEST",
            "customer_id": customer_id,
            "strategy": kwargs["strategy"],
            "items": [
                {
                    "product_id": "PRO00000001",
                    "rank": 1,
                    "score": 1.0,
                    "reason": "training popularity",
                }
            ],
        }

    def list_customer_recommendations(self, customer_id: str, *, limit: int):
        return [{"_id": "REC_TEST", "customer_id": customer_id}][:limit]

    def run_evaluation(self, *, k_values, generation_run_id=None):
        assert generation_run_id is None
        return [
            {"_id": f"EV{k}", "k": k, "metrics": {"precision_at_k": None}}
            for k in k_values
        ]

    def list_evaluation_results(self, *, model_run_id=None, limit: int):
        return [{"_id": "EV_TEST", "model_run_id": model_run_id}][:limit]


async def request(
    method: str, path: str, payload: dict | None = None
):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        return await client.request(method, path, json=payload)


def test_recommendation_generation_and_retrieval_api_does_not_expose_labels() -> None:
    app.dependency_overrides[get_recommendation_service] = (
        lambda: FakeRecommendationService()
    )
    try:
        generated = anyio.run(
            request,
            "POST",
            "/api/v1/recommendations/customers/CUS00000001",
            {
                "strategy": "hybrid",
                "k": 5,
                "as_of_time": "2025-02-01T00:00:00Z",
            },
        )
        retrieved = anyio.run(
            request,
            "GET",
            "/api/v1/recommendations/customers/CUS00000001",
        )
    finally:
        app.dependency_overrides.clear()

    assert generated.status_code == 200
    assert generated.json()["strategy"] == "hybrid"
    assert "ground_truth_labels" not in generated.text
    assert retrieved.status_code == 200
    assert retrieved.json()[0]["_id"] == "REC_TEST"


def test_evaluation_and_strategy_information_endpoints() -> None:
    app.dependency_overrides[get_recommendation_service] = (
        lambda: FakeRecommendationService()
    )
    try:
        evaluated = anyio.run(
            request,
            "POST",
            "/api/v1/recommendations/evaluations",
            {"k_values": [5, 10]},
        )
        results = anyio.run(
            request,
            "GET",
            "/api/v1/recommendations/evaluations?model_run_id=MR_TEST",
        )
    finally:
        app.dependency_overrides.clear()
    strategies = anyio.run(
        request,
        "GET",
        "/api/v1/recommendations/strategies",
    )

    assert evaluated.status_code == 200
    assert [row["k"] for row in evaluated.json()] == [5, 10]
    assert results.status_code == 200
    assert strategies.status_code == 200
    assert strategies.json()["available_strategies"] == [
        "popularity",
        "content",
        "hybrid",
    ]
    assert strategies.json()["ground_truth_labels_are_model_inputs"] is False


def test_recommendation_request_validates_timezone_and_strategy() -> None:
    app.dependency_overrides[get_recommendation_service] = (
        lambda: FakeRecommendationService()
    )
    try:
        naive = anyio.run(
            request,
            "POST",
            "/api/v1/recommendations/customers/CUS00000001",
            {"as_of_time": "2025-02-01T00:00:00"},
        )
        unknown_strategy = anyio.run(
            request,
            "POST",
            "/api/v1/recommendations/customers/CUS00000001",
            {"strategy": "unknown"},
        )
    finally:
        app.dependency_overrides.clear()

    assert naive.status_code == 422
    assert unknown_strategy.status_code == 422


def test_recommendation_api_reports_missing_mongodb_configuration(monkeypatch) -> None:
    import backend.app.api.routes.recommendations as recommendation_routes

    app.dependency_overrides.clear()

    def missing_database():
        raise MongoConfigurationError("MongoDB is not configured.")

    monkeypatch.setattr(recommendation_routes, "get_database", missing_database)

    response = anyio.run(
        request,
        "POST",
        "/api/v1/recommendations/customers/CUS00000001",
        {"strategy": "popularity"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "MongoDB is not configured."
