import anyio
import httpx

from backend.app.main import app


async def get_response(path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        return await client.get(path)


def test_liveness_check_does_not_require_mongodb() -> None:
    response = anyio.run(get_response, "/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_database_health_reports_missing_configuration(
    monkeypatch,
) -> None:
    monkeypatch.delenv("MONGODB_URI", raising=False)

    response = anyio.run(get_response, "/api/v1/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_configured",
        "detail": "MongoDB is not configured. Set the MONGODB_URI environment variable.",
    }
