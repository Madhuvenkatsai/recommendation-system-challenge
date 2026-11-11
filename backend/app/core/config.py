import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

ROOT_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"
DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
)


def load_project_environment() -> None:
    load_dotenv(dotenv_path=ROOT_ENV_PATH, override=False)


load_project_environment()


def cors_allowed_origins() -> tuple[str, ...]:
    configured = os.environ.get("CORS_ALLOWED_ORIGINS", "").strip()
    if not configured:
        return DEFAULT_CORS_ORIGINS
    origins = tuple(
        origin.strip().rstrip("/")
        for origin in configured.split(",")
        if origin.strip()
    )
    for origin in origins:
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
            or origin == "*"
        ):
            raise ValueError(
                "CORS_ALLOWED_ORIGINS must contain explicit HTTP(S) origins only."
            )
    return tuple(dict.fromkeys(origins))


class MongoConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class MongoSettings:
    uri: str
    database_name: str
    collection_prefix: str = ""

    @classmethod
    def from_environment(cls) -> "MongoSettings":
        uri = os.environ.get("MONGODB_URI", "").strip()
        if not uri:
            raise MongoConfigurationError(
                "MongoDB is not configured. Set the MONGODB_URI environment variable."
            )

        database_name = os.environ.get(
            "MONGODB_DATABASE", "recommendation_challenge"
        ).strip()
        if not database_name:
            raise MongoConfigurationError(
                "MongoDB is not configured. MONGODB_DATABASE must not be empty."
            )

        collection_prefix = os.environ.get(
            "MONGODB_COLLECTION_PREFIX", ""
        ).strip()
        if collection_prefix and not re.fullmatch(
            r"[a-z][a-z0-9_]{0,29}_", collection_prefix
        ):
            raise MongoConfigurationError(
                "MONGODB_COLLECTION_PREFIX must be a lowercase collection namespace "
                "ending in an underscore, such as 'full_'."
            )

        return cls(
            uri=uri,
            database_name=database_name,
            collection_prefix=collection_prefix,
        )
