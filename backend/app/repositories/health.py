from backend.app.db.mongo import get_database


def check_database() -> None:
    get_database().command("ping")
