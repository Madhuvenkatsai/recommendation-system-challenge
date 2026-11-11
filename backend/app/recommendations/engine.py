from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import blake2b
import json
from typing import Any, Iterable, Literal, Mapping

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from backend.app.generator.config import GENERATION_SEED

Strategy = Literal["popularity", "content", "hybrid"]
STRATEGIES: tuple[Strategy, ...] = ("popularity", "content", "hybrid")
MODEL_VERSION = "recommendation-v1"
EVENT_WEIGHTS = {"view": 1.0, "cart": 3.0, "purchase": 5.0}
PURCHASE_EXCLUSION_RULE = "exclude_completed_purchases_before_as_of_time_v1"


@dataclass(frozen=True)
class Interaction:
    customer_id: str
    product_id: str
    occurred_at: datetime
    event_type: Literal["view", "cart", "purchase"]
    source_id: str
    session_id: str | None = None


@dataclass
class ProductHistory:
    weight: float = 0.0
    source_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RecommendationItem:
    product_id: str
    rank: int
    score: float
    reason: str
    source_interaction_ids: list[str]
    eligibility_status: str = "eligible"

    def as_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "rank": self.rank,
            "score": self.score,
            "reason": self.reason,
            "source_interaction_ids": self.source_interaction_ids,
            "eligibility_status": self.eligibility_status,
        }


@dataclass(frozen=True)
class RecommendationResult:
    customer_id: str
    session_id: str | None
    requested_at: datetime
    as_of_time: datetime
    training_cutoff: datetime
    generation_run_id: str
    strategy: Strategy
    k: int
    model_version: str
    model_run_id: str
    source_interaction_ids: list[str]
    items: list[RecommendationItem]

    def as_document(self) -> dict[str, Any]:
        stable_key = "|".join(
            (
                self.generation_run_id,
                self.customer_id,
                self.as_of_time.isoformat(),
                self.strategy,
                str(self.k),
                self.model_run_id,
            )
        )
        recommendation_id = "REC" + blake2b(
            stable_key.encode("utf-8"), digest_size=12
        ).hexdigest().upper()
        return {
            "_id": recommendation_id,
            "customer_id": self.customer_id,
            "session_id": self.session_id,
            "model_run_id": self.model_run_id,
            "generation_run_id": self.generation_run_id,
            "strategy": self.strategy,
            "k": self.k,
            "model_version": self.model_version,
            "source_interaction_ids": self.source_interaction_ids,
            "requested_at": self.requested_at,
            "as_of_time": self.as_of_time,
            "training_cutoff": self.training_cutoff,
            "purchased_exclusion_rule": PURCHASE_EXCLUSION_RULE,
            "status": "valid",
            "items": [item.as_dict() for item in self.items],
        }


def is_available_at(product: Mapping[str, Any], at: datetime) -> bool:
    """Resolve the product lifecycle at a timestamp, not from its current status alone."""
    created_at = product.get("created_at")
    available_from = product.get("available_from")
    available_to = product.get("available_to")
    if isinstance(created_at, datetime) and created_at > at:
        return False
    if isinstance(available_from, datetime) and available_from > at:
        return False
    if isinstance(available_to, datetime) and at >= available_to:
        return False
    status = product.get("status")
    if status == "unavailable":
        return False
    if status == "discontinued":
        return isinstance(available_to, datetime) and at < available_to
    return status == "active"


def _price_band(product: Mapping[str, Any]) -> str:
    price = product.get("price", 0)
    if hasattr(price, "to_decimal"):
        price = price.to_decimal()
    value = float(price)
    upper_bounds = (10, 25, 50, 100, 250, 500)
    lower = 0
    for upper in upper_bounds:
        if value < upper:
            return f"priceband{lower}to{upper}"
        lower = upper
    return f"priceband{lower}plus"


def _product_text(
    product: Mapping[str, Any], categories: Mapping[str, Mapping[str, Any]]
) -> str:
    category_id = product.get("category_id")
    category = categories.get(category_id, {})
    attributes = product.get("attributes", {})
    category_index = attributes.get("category_index")
    tokens = [
        str(product.get("name", "")),
        str(product.get("description", "")),
        str(product.get("brand") or ""),
        str(category.get("name", "")),
        str(category.get("slug", "")),
        f"categoryindex{category_index}" if category_index is not None else "",
        _price_band(product),
    ]
    return " ".join(token for token in tokens if token)


def _normalized(scores: Mapping[str, float]) -> dict[str, float]:
    maximum = max(scores.values(), default=0.0)
    if maximum <= 0:
        return {product_id: 0.0 for product_id in scores}
    return {
        product_id: max(0.0, score) / maximum
        for product_id, score in scores.items()
    }


class RecommendationEngine:
    """Training-window popularity and TF-IDF content recommendation strategies."""

    def __init__(
        self,
        products: Iterable[Mapping[str, Any]],
        categories: Iterable[Mapping[str, Any]],
        interactions: Iterable[Interaction],
        *,
        training_cutoff: datetime,
        generation_run_id: str,
        seed: int = GENERATION_SEED,
        popularity_weight: float = 0.5,
        content_weight: float = 0.5,
        cold_start_interaction_threshold: int = 2,
    ) -> None:
        if training_cutoff.tzinfo is None:
            raise ValueError("training_cutoff must be timezone-aware.")
        if seed != GENERATION_SEED:
            raise ValueError(f"seed is fixed at {GENERATION_SEED}.")
        if popularity_weight < 0 or content_weight < 0:
            raise ValueError("Hybrid weights must be non-negative.")
        if popularity_weight + content_weight <= 0:
            raise ValueError("At least one hybrid weight must be positive.")
        if cold_start_interaction_threshold < 1:
            raise ValueError("cold_start_interaction_threshold must be positive.")

        self.training_cutoff = training_cutoff
        self.generation_run_id = generation_run_id
        self.seed = seed
        total_weight = popularity_weight + content_weight
        self.popularity_weight = popularity_weight / total_weight
        self.content_weight = content_weight / total_weight
        self.cold_start_interaction_threshold = cold_start_interaction_threshold
        self.categories = {
            str(category["_id"]): category
            for category in categories
            if isinstance(category.get("_id"), str)
        }
        self.products = {
            str(product["_id"]): product
            for product in products
            if isinstance(product.get("_id"), str)
        }
        self.product_ids = sorted(self.products)
        self.popularity: dict[str, float] = defaultdict(float)
        self.interaction_counts: dict[str, int] = defaultdict(int)
        self.profiles: dict[str, dict[str, ProductHistory]] = defaultdict(dict)
        self.session_by_customer: dict[str, str] = {}
        self._source_ids_by_customer: dict[str, list[str]] = defaultdict(list)
        self._profile_times: dict[str, datetime] = {}

        for event in interactions:
            if event.event_type not in EVENT_WEIGHTS:
                continue
            if event.occurred_at.tzinfo is None:
                raise ValueError("Interaction timestamps must be timezone-aware.")
            if event.occurred_at >= training_cutoff:
                continue
            if event.customer_id == "" or event.product_id not in self.products:
                continue
            weight = EVENT_WEIGHTS[event.event_type]
            self.popularity[event.product_id] += weight
            self.interaction_counts[event.product_id] += 1
            history = self.profiles[event.customer_id].setdefault(
                event.product_id, ProductHistory()
            )
            history.weight += weight
            if event.source_id and len(history.source_ids) < 20:
                history.source_ids.append(event.source_id)
            if (
                event.session_id
                and event.occurred_at >= self._latest_profile_time(
                    event.customer_id
                )
            ):
                self.session_by_customer[event.customer_id] = event.session_id
                self._profile_times[event.customer_id] = event.occurred_at
            if event.source_id and len(self._source_ids_by_customer[event.customer_id]) < 100:
                self._source_ids_by_customer[event.customer_id].append(event.source_id)

        self.vectorizer = TfidfVectorizer(
            lowercase=True,
            ngram_range=(1, 2),
            token_pattern=r"(?u)\b\w+\b",
            stop_words=["product", "item", "category"],
            dtype=np.float32,
        )
        training_products = [
            self.products[product_id]
            for product_id in self.product_ids
            if not isinstance(self.products[product_id].get("created_at"), datetime)
            or self.products[product_id]["created_at"] < training_cutoff
        ]
        training_text = [
            _product_text(product, self.categories) for product in training_products
        ]
        analyzer = self.vectorizer.build_analyzer()
        usable_training_text = [
            text for text in training_text if next(iter(analyzer(text)), None)
        ]
        if usable_training_text:
            self.vectorizer.fit(usable_training_text)
            self._product_matrix = self.vectorizer.transform(
                [
                    _product_text(self.products[product_id], self.categories)
                    for product_id in self.product_ids
                ]
            )
        else:
            self._product_matrix = None
        self._product_index = {
            product_id: index for index, product_id in enumerate(self.product_ids)
        }
        self.model_run_ids = {
            strategy: self._model_run_id(strategy) for strategy in STRATEGIES
        }

    def _latest_profile_time(self, customer_id: str) -> datetime:
        return self._profile_times.get(customer_id, datetime.min.replace(tzinfo=self.training_cutoff.tzinfo))

    def _model_run_id(self, strategy: Strategy) -> str:
        parameters = json.dumps(
            {
                "version": MODEL_VERSION,
                "seed": self.seed,
                "popularity_weight": self.popularity_weight,
                "content_weight": self.content_weight,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = blake2b(
            f"{self.generation_run_id}|{strategy}|{parameters}".encode("utf-8"),
            digest_size=10,
        ).hexdigest().upper()
        return f"MR{digest}"

    def model_run_document(self, strategy: Strategy) -> dict[str, Any]:
        return {
            "_id": self.model_run_ids[strategy],
            "algorithm": strategy,
            "model_version": MODEL_VERSION,
            "dataset_version": (
                f"DS{self.generation_run_id[3:]}"
                if self.generation_run_id.startswith("RUN")
                else self.generation_run_id
            ),
            "training_split_id": (
                f"SPL{self.generation_run_id[3:]}TRAIN"
                if self.generation_run_id.startswith("RUN")
                else self.generation_run_id
            ),
            "training_cutoff": self.training_cutoff,
            "parameters": {
                "seed": self.seed,
                "event_weights": EVENT_WEIGHTS,
                "popularity_weight": self.popularity_weight,
                "content_weight": self.content_weight,
                "cold_start_interaction_threshold": self.cold_start_interaction_threshold,
            },
            "feature_sources": [
                "products",
                "categories",
                "page_views",
                "cart_lines",
                "orders",
                "order_lines",
            ],
            "status": "completed",
            "created_at": self.training_cutoff,
            "completed_at": self.training_cutoff,
        }

    def eligible_catalog(self, as_of_time: datetime) -> list[Mapping[str, Any]]:
        return [
            self.products[product_id]
            for product_id in self.product_ids
            if is_available_at(self.products[product_id], as_of_time)
        ]

    def cold_start_products(self, as_of_time: datetime) -> set[str]:
        return {
            str(product["_id"])
            for product in self.eligible_catalog(as_of_time)
            if product.get("is_cold_start", False)
            or self.interaction_counts.get(str(product["_id"]), 0)
            < self.cold_start_interaction_threshold
        }

    def _content_scores(
        self,
        customer_id: str,
        candidate_ids: list[str],
    ) -> tuple[dict[str, float], dict[str, list[str]]]:
        scores: dict[str, float] = {product_id: 0.0 for product_id in candidate_ids}
        evidence: dict[str, list[str]] = defaultdict(list)
        profile = self.profiles.get(customer_id, {})
        if not profile or self._product_matrix is None or not candidate_ids:
            return scores, evidence
        history_ids = [
            product_id
            for product_id in sorted(profile)
            if product_id in self._product_index
        ]
        if not history_ids:
            return scores, evidence
        candidate_indices = [self._product_index[product_id] for product_id in candidate_ids]
        candidate_matrix = self._product_matrix[candidate_indices]
        history_indices = [self._product_index[product_id] for product_id in history_ids]
        history_matrix = self._product_matrix[history_indices]
        similarities = cosine_similarity(
            history_matrix,
            candidate_matrix,
            dense_output=False,
        )
        for history_position, history_id in enumerate(history_ids):
            history = profile[history_id]
            row_start = similarities.indptr[history_position]
            row_end = similarities.indptr[history_position + 1]
            for candidate_position, similarity_value in zip(
                similarities.indices[row_start:row_end],
                similarities.data[row_start:row_end],
            ):
                product_id = candidate_ids[int(candidate_position)]
                similarity = float(similarity_value)
                if similarity > 0:
                    scores[product_id] += similarity * history.weight
                    if history.source_ids and len(evidence[product_id]) < 20:
                        evidence[product_id].extend(
                            source_id
                            for source_id in history.source_ids
                            if source_id not in evidence[product_id]
                        )
        total_history_weight = sum(history.weight for history in profile.values())
        if total_history_weight > 0:
            scores = {
                product_id: score / total_history_weight
                for product_id, score in scores.items()
            }
        return scores, evidence

    def recommend(
        self,
        customer_id: str,
        *,
        strategy: Strategy,
        as_of_time: datetime,
        k: int = 10,
        purchased_product_ids: Iterable[str] = (),
        session_id: str | None = None,
        requested_at: datetime | None = None,
    ) -> RecommendationResult:
        if strategy not in STRATEGIES:
            raise ValueError(f"Unsupported strategy: {strategy}.")
        if as_of_time.tzinfo is None:
            raise ValueError("as_of_time must be timezone-aware.")
        if as_of_time < self.training_cutoff:
            raise ValueError("as_of_time cannot precede the training cutoff.")
        if k < 1:
            raise ValueError("k must be at least one.")
        requested_at = requested_at or as_of_time
        if requested_at.tzinfo is None:
            raise ValueError("requested_at must be timezone-aware.")

        purchased = set(purchased_product_ids)
        candidates = [
            product
            for product in self.eligible_catalog(as_of_time)
            if product["_id"] not in purchased
        ]
        candidate_ids = sorted(str(product["_id"]) for product in candidates)
        popularity_scores = _normalized(
            {
                product_id: self.popularity.get(product_id, 0.0)
                for product_id in candidate_ids
            }
        )
        no_history = not self.profiles.get(customer_id)
        if strategy == "popularity" or no_history:
            raw_content: dict[str, float] = {}
            content_evidence: dict[str, list[str]] = {}
        else:
            raw_content, content_evidence = self._content_scores(
                customer_id, candidate_ids
            )
        content_scores = _normalized(
            raw_content
            if raw_content
            else {product_id: 0.0 for product_id in candidate_ids}
        )
        effective_strategy = "popularity" if no_history and strategy != "popularity" else strategy

        if effective_strategy == "popularity":
            combined = popularity_scores
        elif effective_strategy == "content":
            combined = content_scores
        else:
            combined = {
                product_id: (
                    popularity_scores[product_id] * self.popularity_weight
                    + content_scores[product_id] * self.content_weight
                )
                for product_id in candidate_ids
            }

        products_by_id = {str(product["_id"]): product for product in candidates}
        category_weights: dict[str, float] = defaultdict(float)
        for history_id, history in self.profiles.get(customer_id, {}).items():
            product = self.products.get(history_id, {})
            category_id = product.get("category_id")
            if isinstance(category_id, str):
                category_weights[category_id] += history.weight
        ranked = sorted(candidate_ids, key=lambda product_id: (-combined[product_id], product_id))
        items: list[RecommendationItem] = []
        for rank, product_id in enumerate(ranked[:k], start=1):
            product = products_by_id[product_id]
            if no_history:
                reason = "No training-period customer history; using training-period popularity fallback."
            elif (
                strategy == "popularity"
                and self.popularity.get(product_id, 0.0) > 0
            ):
                reason = "Frequently viewed, carted, or purchased during the training period."
            elif product.get("is_cold_start", False) or self.interaction_counts.get(
                product_id, 0
            ) < self.cold_start_interaction_threshold:
                reason = "Cold-start product selected using available product attributes."
            elif (
                product.get("category_id") in category_weights
                and strategy in {"content", "hybrid"}
            ):
                reason = "Similar category to the customer's training-period interactions."
            elif strategy == "hybrid":
                reason = "Hybrid relevance combines normalized popularity and content similarity."
            else:
                reason = "Similar product attributes to the customer's training-period interactions."
            source_ids = (
                content_evidence.get(product_id, [])[:10]
                if strategy in {"content", "hybrid"}
                else []
            )
            items.append(
                RecommendationItem(
                    product_id=product_id,
                    rank=rank,
                    score=round(combined[product_id], 8),
                    reason=reason,
                    source_interaction_ids=source_ids,
                )
            )

        source_ids = self._source_ids_by_customer.get(customer_id, [])[-100:]
        result_session = session_id or self.session_by_customer.get(customer_id)
        return RecommendationResult(
            customer_id=customer_id,
            session_id=result_session,
            requested_at=requested_at,
            as_of_time=as_of_time,
            training_cutoff=self.training_cutoff,
            generation_run_id=self.generation_run_id,
            strategy=strategy,
            k=k,
            model_version=MODEL_VERSION,
            model_run_id=self.model_run_ids[strategy],
            source_interaction_ids=source_ids,
            items=items,
        )
