from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

GENERATION_SEED = 20261022
DEFAULT_START = datetime(2024, 1, 1, tzinfo=timezone.utc)
DEFAULT_END = datetime(2026, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class GenerationConfig:
    customers: int = 20_000
    products: int = 10_000
    categories: int = 40
    sessions: int = 500_000
    orders: int = 100_000
    page_views_per_session: int = 3
    carts: int | None = None
    seed: int = GENERATION_SEED
    start_at: datetime = DEFAULT_START
    end_at: datetime = DEFAULT_END

    def __post_init__(self) -> None:
        counts = {
            "customers": self.customers,
            "products": self.products,
            "categories": self.categories,
            "sessions": self.sessions,
            "orders": self.orders,
            "page_views_per_session": self.page_views_per_session,
        }
        for name, value in counts.items():
            if value < 1:
                raise ValueError(f"{name} must be at least one.")
        if self.customers < 2:
            raise ValueError("customers must be at least two.")
        if self.categories < 8:
            raise ValueError("categories must be at least eight.")
        if self.products < self.categories:
            raise ValueError("products must be greater than or equal to categories.")
        if max(self.categories, int(self.products * 0.8)) < self.categories * 2:
            raise ValueError(
                "the popular catalog must contain at least two products per category."
            )
        max_page_views = self.page_views_per_session * 2 - 1
        if max_page_views > max(self.categories, int(self.products * 0.8)):
            raise ValueError(
                "the maximum session page views cannot exceed the popular product count."
            )
        if self.seed != GENERATION_SEED:
            raise ValueError(f"seed is fixed at {GENERATION_SEED}.")
        if self.start_at.tzinfo is None or self.end_at.tzinfo is None:
            raise ValueError("start_at and end_at must be timezone-aware.")
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at.")
        if self.sessions < self.orders:
            raise ValueError("sessions must be greater than or equal to orders.")
        if self.cart_count < self.orders:
            raise ValueError("cart count must be greater than or equal to orders.")
        if self.cart_count > self.sessions:
            raise ValueError("cart count must not exceed sessions.")
        if self.timeline_seconds <= 86_400:
            raise ValueError("generation timeline must exceed one day.")

    @property
    def cart_count(self) -> int:
        return self.carts if self.carts is not None else max(
            self.orders, self.sessions // 2
        )

    @property
    def timeline_seconds(self) -> int:
        return int((self.end_at - self.start_at).total_seconds())

    @classmethod
    def full(cls) -> "GenerationConfig":
        return cls()

    @classmethod
    def starter(cls) -> "GenerationConfig":
        return cls(
            customers=200,
            products=100,
            categories=12,
            sessions=2_500,
            orders=500,
        )

    def as_dict(self) -> dict[str, Any]:
        values = asdict(self)
        values["carts"] = self.cart_count
        values["start_at"] = self.start_at.isoformat()
        values["end_at"] = self.end_at.isoformat()
        return values
