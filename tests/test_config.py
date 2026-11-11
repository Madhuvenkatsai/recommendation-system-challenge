from pathlib import Path

import pytest

from backend.app.core import config
from backend.app.core.config import (
    DEFAULT_CORS_ORIGINS,
    MongoConfigurationError,
    MongoSettings,
    cors_allowed_origins,
)


def test_missing_env_file_does_not_configure_mongodb(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(config, "ROOT_ENV_PATH", tmp_path / "missing.env")
    monkeypatch.delenv("MONGODB_URI", raising=False)
    monkeypatch.delenv("MONGODB_DATABASE", raising=False)

    config.load_project_environment()

    with pytest.raises(MongoConfigurationError, match="MONGODB_URI"):
        MongoSettings.from_environment()


def test_missing_mongodb_uri_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("MONGODB_DATABASE=test-database\n", encoding="utf-8")
    monkeypatch.setattr(config, "ROOT_ENV_PATH", env_file)
    monkeypatch.delenv("MONGODB_URI", raising=False)
    monkeypatch.delenv("MONGODB_DATABASE", raising=False)

    config.load_project_environment()

    with pytest.raises(MongoConfigurationError, match="MONGODB_URI"):
        MongoSettings.from_environment()


def test_valid_environment_configuration_is_loaded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "MONGODB_URI=configured-uri\nMONGODB_DATABASE=configured-database\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "ROOT_ENV_PATH", env_file)
    monkeypatch.delenv("MONGODB_URI", raising=False)
    monkeypatch.delenv("MONGODB_DATABASE", raising=False)

    config.load_project_environment()
    settings = MongoSettings.from_environment()

    assert settings.uri == "configured-uri"
    assert settings.database_name == "configured-database"


def test_database_defaults_to_the_challenge_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MONGODB_URI", "configured-uri")
    monkeypatch.delenv("MONGODB_DATABASE", raising=False)

    assert MongoSettings.from_environment().database_name == "recommendation_challenge"


def test_process_environment_takes_precedence_over_env_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "MONGODB_URI=dotenv-uri\nMONGODB_DATABASE=dotenv-database\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "ROOT_ENV_PATH", env_file)
    monkeypatch.setenv("MONGODB_URI", "process-uri")
    monkeypatch.setenv("MONGODB_DATABASE", "process-database")

    config.load_project_environment()
    settings = MongoSettings.from_environment()

    assert settings.uri == "process-uri"
    assert settings.database_name == "process-database"


def test_collection_namespace_is_optional_and_validated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MONGODB_URI", "configured-uri")
    monkeypatch.setenv("MONGODB_DATABASE", "configured-database")
    monkeypatch.delenv("MONGODB_COLLECTION_PREFIX", raising=False)
    assert MongoSettings.from_environment().collection_prefix == ""

    monkeypatch.setenv("MONGODB_COLLECTION_PREFIX", "full_")
    assert MongoSettings.from_environment().collection_prefix == "full_"

    monkeypatch.setenv("MONGODB_COLLECTION_PREFIX", "full")
    with pytest.raises(MongoConfigurationError, match="collection namespace"):
        MongoSettings.from_environment()


def test_cors_origins_default_to_local_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)

    assert cors_allowed_origins() == DEFAULT_CORS_ORIGINS


def test_cors_origins_accept_explicit_production_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        "https://shop.example, https://admin.example/",
    )

    assert cors_allowed_origins() == (
        "https://shop.example",
        "https://admin.example",
    )


def test_cors_origins_reject_wildcard_and_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")

    with pytest.raises(ValueError, match="explicit HTTP"):
        cors_allowed_origins()
