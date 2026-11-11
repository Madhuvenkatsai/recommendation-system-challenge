from collections import defaultdict
from datetime import datetime, timezone
from hashlib import blake2b
from itertools import islice
from typing import Any, Iterable

from pymongo.database import Database

from backend.app.generator.config import GENERATION_SEED
from backend.app.repositories.evaluation import get_evaluation_repositories
from backend.app.repositories.model_input import get_model_input_repositories
from backend.app.recommendations.engine import (
    EVENT_WEIGHTS,
    MODEL_VERSION,
    STRATEGIES,
    Interaction,
    RecommendationEngine,
    Strategy,
)
from backend.app.recommendations.metrics import RankingMetrics

TRAINING_FEATURE_SOURCES = (
    "products",
    "categories",
    "page_views",
    "cart_lines",
    "orders",
    "order_lines",
)


class RecommendationService:
    def __init__(
        self,
        database: Database | Any,
        *,
        batch_size: int = 1_000,
        popularity_weight: float = 0.5,
        content_weight: float = 0.5,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be greater than zero.")
        self.database = database
        self.model_input = get_model_input_repositories(database)
        self.evaluation = get_evaluation_repositories(database)
        self.batch_size = batch_size
        self.popularity_weight = popularity_weight
        self.content_weight = content_weight
        self._cached_run_id: str | None = None
        self._cached_engine: RecommendationEngine | None = None
        self._cached_splits: dict[str, dict[str, Any]] = {}

    def _generation_run(self, generation_run_id: str | None = None) -> dict[str, Any]:
        if generation_run_id:
            record = self.model_input.generation_runs.get_by_id(generation_run_id)
        else:
            record = self.database["generation_runs"].find_one(
                {"status": "completed"},
                sort=[("completed_at", -1), ("_id", 1)],
            )
        if not record or record.get("status") != "completed":
            raise LookupError("No matching completed generation run was found.")
        return record

    def _split(
        self, dataset_version: str, split_name: str
    ) -> dict[str, Any]:
        record = self.evaluation.dataset_splits.collection.find_one(
            {"dataset_version": dataset_version, "split_name": split_name}
        )
        if not record:
            raise LookupError(
                f"Dataset {dataset_version!r} has no {split_name!r} split."
            )
        return record

    def _training_interactions(
        self, start_at: datetime, cutoff: datetime
    ) -> Iterable[Interaction]:
        if start_at.tzinfo is None or cutoff.tzinfo is None or start_at >= cutoff:
            raise ValueError(
                "The training window must be a valid timezone-aware interval."
            )
        page_views = self.model_input.page_views.iter_many(
            {"occurred_at": {"$gte": start_at, "$lt": cutoff}},
            projection={
                "_id": 1,
                "customer_id": 1,
                "product_id": 1,
                "session_id": 1,
                "occurred_at": 1,
            },
            batch_size=self.batch_size,
            sort=[("occurred_at", 1), ("_id", 1)],
        )
        for row in page_views:
            yield Interaction(
                customer_id=row["customer_id"],
                product_id=row["product_id"],
                occurred_at=row["occurred_at"],
                event_type="view",
                source_id=row["_id"],
                session_id=row.get("session_id"),
            )

        cart_pipeline = [
            {"$match": {"added_at": {"$gte": start_at, "$lt": cutoff}}},
            {
                "$lookup": {
                    "from": "carts",
                    "localField": "cart_id",
                    "foreignField": "_id",
                    "as": "_cart",
                }
            },
            {"$unwind": "$_cart"},
            {
                "$project": {
                    "_id": 1,
                    "customer_id": "$_cart.customer_id",
                    "session_id": "$_cart.session_id",
                    "product_id": 1,
                    "occurred_at": "$added_at",
                }
            },
            {"$sort": {"occurred_at": 1, "_id": 1}},
        ]
        for row in self.model_input.cart_lines.iter_aggregate(
            cart_pipeline, batch_size=self.batch_size
        ):
            yield Interaction(
                customer_id=row["customer_id"],
                product_id=row["product_id"],
                occurred_at=row["occurred_at"],
                event_type="cart",
                source_id=row["_id"],
                session_id=row.get("session_id"),
            )

        purchase_pipeline = [
            {
                "$match": {
                    "status": "completed",
                    "placed_at": {"$gte": start_at, "$lt": cutoff},
                }
            },
            {
                "$lookup": {
                    "from": "order_lines",
                    "localField": "_id",
                    "foreignField": "order_id",
                    "as": "_lines",
                }
            },
            {"$unwind": "$_lines"},
            {
                "$project": {
                    "_id": "$_lines._id",
                    "customer_id": 1,
                    "session_id": 1,
                    "product_id": "$_lines.product_id",
                    "occurred_at": "$placed_at",
                }
            },
            {"$sort": {"occurred_at": 1, "_id": 1}},
        ]
        for row in self.model_input.orders.iter_aggregate(
            purchase_pipeline, batch_size=self.batch_size
        ):
            yield Interaction(
                customer_id=row["customer_id"],
                product_id=row["product_id"],
                occurred_at=row["occurred_at"],
                event_type="purchase",
                source_id=row["_id"],
                session_id=row.get("session_id"),
            )

    def _load_model(
        self, generation_run_id: str | None = None
    ) -> tuple[dict[str, Any], RecommendationEngine, dict[str, dict[str, Any]]]:
        run = self._generation_run(generation_run_id)
        run_id = run["_id"]
        if self._cached_run_id == run_id and self._cached_engine is not None:
            return run, self._cached_engine, self._cached_splits

        dataset_version = (
            f"DS{run_id[3:]}" if run_id.startswith("RUN") else run_id
        )
        train_split = self._split(dataset_version, "train")
        splits = {"train": train_split}
        for name in ("validation", "test"):
            try:
                splits[name] = self._split(dataset_version, name)
            except LookupError:
                if name == "test":
                    raise
        cutoff = train_split["end_at"]
        products = list(
            self.model_input.products.iter_many(
                {},
                batch_size=self.batch_size,
                sort=[("_id", 1)],
            )
        )
        categories = list(
            self.model_input.categories.iter_many(
                {},
                batch_size=self.batch_size,
                sort=[("_id", 1)],
            )
        )
        engine = RecommendationEngine(
            products,
            categories,
            self._training_interactions(train_split["start_at"], cutoff),
            training_cutoff=cutoff,
            generation_run_id=run_id,
            seed=GENERATION_SEED,
            popularity_weight=self.popularity_weight,
            content_weight=self.content_weight,
        )
        self._cached_run_id = run_id
        self._cached_engine = engine
        self._cached_splits = splits
        return run, engine, splits

    def _purchased_before(
        self,
        customer_id: str,
        as_of_time: datetime,
    ) -> set[str]:
        pipeline = [
            {
                "$match": {
                    "customer_id": customer_id,
                    "status": "completed",
                    "placed_at": {"$lt": as_of_time},
                }
            },
            {
                "$lookup": {
                    "from": "order_lines",
                    "localField": "_id",
                    "foreignField": "order_id",
                    "as": "_lines",
                }
            },
            {"$unwind": "$_lines"},
            {"$project": {"product_id": "$_lines.product_id"}},
        ]
        return {
            row["product_id"]
            for row in self.model_input.orders.iter_aggregate(
                pipeline, batch_size=self.batch_size
            )
        }

    def _purchases_before_by_customer(
        self, as_of_time: datetime
    ) -> dict[str, set[str]]:
        pipeline = [
            {
                "$match": {
                    "status": "completed",
                    "placed_at": {"$lt": as_of_time},
                }
            },
            {
                "$lookup": {
                    "from": "order_lines",
                    "localField": "_id",
                    "foreignField": "order_id",
                    "as": "_lines",
                }
            },
            {"$unwind": "$_lines"},
            {
                "$project": {
                    "customer_id": 1,
                    "product_id": "$_lines.product_id",
                }
            },
            {"$sort": {"customer_id": 1, "product_id": 1}},
        ]
        purchased: dict[str, set[str]] = defaultdict(set)
        for row in self.model_input.orders.iter_aggregate(
            pipeline, batch_size=self.batch_size
        ):
            purchased[row["customer_id"]].add(row["product_id"])
        return purchased

    def _upsert_model_run(
        self,
        engine: RecommendationEngine,
        strategy: Strategy,
    ) -> None:
        self.model_input.model_runs.upsert_by_id(
            engine.model_run_document(strategy)
        )

    def generate_for_customer(
        self,
        customer_id: str,
        *,
        strategy: Strategy = "hybrid",
        k: int = 10,
        as_of_time: datetime | None = None,
        session_id: str | None = None,
        generation_run_id: str | None = None,
    ) -> dict[str, Any]:
        _, engine, _ = self._load_model(generation_run_id)
        if self.model_input.customers.get_by_id(customer_id) is None:
            raise LookupError(f"Customer {customer_id!r} was not found.")
        requested_at = datetime.now(timezone.utc)
        as_of_time = as_of_time or requested_at
        if session_id:
            session = self.model_input.sessions.get_by_id(session_id)
            if session is None:
                raise LookupError(f"Session {session_id!r} was not found.")
            if session.get("customer_id") != customer_id:
                raise ValueError("session_id must belong to the requested customer.")
        result = engine.recommend(
            customer_id,
            strategy=strategy,
            as_of_time=as_of_time,
            k=k,
            purchased_product_ids=self._purchased_before(customer_id, as_of_time),
            session_id=session_id,
            requested_at=requested_at,
        )
        self._upsert_model_run(engine, strategy)
        document = result.as_document()
        self.model_input.recommendations.upsert_by_id(document)
        return document

    def list_customer_recommendations(
        self, customer_id: str, *, limit: int = 50
    ) -> list[dict[str, Any]]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500.")
        rows = self.model_input.recommendations.iter_many(
            {"customer_id": customer_id},
            batch_size=min(limit, self.batch_size),
            sort=[("requested_at", -1), ("_id", 1)],
        )
        return list(islice(rows, limit))

    def run_evaluation(
        self,
        *,
        k_values: Iterable[int] = (5, 10),
        generation_run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        ks = sorted(set(k_values))
        if not ks or any(k < 1 for k in ks):
            raise ValueError("k_values must contain positive integers.")
        _, engine, splits = self._load_model(generation_run_id)
        test_split = splits.get("test")
        if test_split is None:
            raise LookupError("The generation run has no test split.")
        as_of_time = test_split["start_at"]
        eligible_products = engine.eligible_catalog(as_of_time)
        eligible_catalog_ids = {
            str(product["_id"]) for product in eligible_products
        }
        cold_start_ids = engine.cold_start_products(as_of_time)

        labels_by_customer: dict[str, set[str]] = defaultdict(set)
        source_label_counts: dict[str, int] = defaultdict(int)
        for label in self.evaluation.ground_truth_labels.iter_many(
            {
                "dataset_split_id": test_split["_id"],
                "event_type": "purchase",
            },
            batch_size=self.batch_size,
            sort=[("customer_id", 1), ("occurred_at", 1), ("_id", 1)],
        ):
            product_id = label["product_id"]
            labels_by_customer[label["customer_id"]].add(product_id)
            source_label_counts[label["customer_id"]] += 1

        purchased_before = self._purchases_before_by_customer(as_of_time)
        eligible_relevant: dict[str, set[str]] = {}
        for customer_id, products in labels_by_customer.items():
            purchased = purchased_before.get(customer_id, set())
            relevant = {
                product_id
                for product_id in products
                if product_id in eligible_catalog_ids and product_id not in purchased
            }
            eligible_relevant[customer_id] = relevant

        results: list[dict[str, Any]] = []
        for strategy in STRATEGIES:
            self._upsert_model_run(engine, strategy)
            accumulators = {
                k: RankingMetrics(
                    k=k,
                    eligible_catalog_ids=eligible_catalog_ids,
                    cold_start_catalog_ids=cold_start_ids,
                )
                for k in ks
            }
            batch: list[dict[str, Any]] = []
            for customer_id in sorted(labels_by_customer):
                relevant = eligible_relevant[customer_id]
                if not relevant:
                    for accumulator in accumulators.values():
                        accumulator.add_user(
                            (),
                            (),
                            source_label_count=source_label_counts[customer_id],
                        )
                    continue
                recommendation = engine.recommend(
                    customer_id,
                    strategy=strategy,
                    as_of_time=as_of_time,
                    k=max(ks),
                    purchased_product_ids=purchased_before.get(customer_id, ()),
                )
                recommendation_doc = recommendation.as_document()
                batch.append(recommendation_doc)
                recommended_ids = [
                    item.product_id for item in recommendation.items
                ]
                for accumulator in accumulators.values():
                    accumulator.add_user(
                        recommended_ids,
                        relevant,
                        source_label_count=source_label_counts[customer_id],
                    )
                if len(batch) >= self.batch_size:
                    self.model_input.recommendations.upsert_many_by_id(batch)
                    batch = []
            if batch:
                self.model_input.recommendations.upsert_many_by_id(batch)

            for k, accumulator in accumulators.items():
                metrics = accumulator.as_metrics()
                result_id = "EV" + blake2b(
                    (
                        f"{engine.model_run_ids[strategy]}|{test_split['_id']}|{k}"
                    ).encode("utf-8"),
                    digest_size=12,
                ).hexdigest().upper()
                document = {
                    "_id": result_id,
                    "model_run_id": engine.model_run_ids[strategy],
                    "strategy": strategy,
                    "model_version": MODEL_VERSION,
                    "dataset_split_id": test_split["_id"],
                    "k": k,
                    "evaluated_at": datetime.now(timezone.utc),
                    "sample_count": accumulator.evaluable_users,
                    "metrics": metrics,
                }
                self.evaluation.evaluation_results.upsert_by_id(document)
                results.append(document)
        return results

    def list_evaluation_results(
        self,
        *,
        model_run_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500.")
        query = {"model_run_id": model_run_id} if model_run_id else {}
        results = list(
            islice(
                self.evaluation.evaluation_results.iter_many(
                    query,
                    batch_size=min(limit, self.batch_size),
                    sort=[("evaluated_at", -1), ("_id", 1)],
                ),
                limit,
            )
        )
        model_ids = {
            result["model_run_id"]
            for result in results
            if result.get("model_run_id")
        }
        models = {
            model["_id"]: model
            for model in self.evaluation.model_runs.find_many(
                {"_id": {"$in": list(model_ids)}},
                limit=max(1, len(model_ids)),
                projection={"_id": 1, "algorithm": 1, "model_version": 1},
            )
        }
        for result in results:
            model = models.get(result.get("model_run_id"), {})
            result.setdefault("strategy", model.get("algorithm"))
            result.setdefault("model_version", model.get("model_version"))
        return results

    @staticmethod
    def strategy_information() -> dict[str, Any]:
        return {
            "model_version": MODEL_VERSION,
            "seed": GENERATION_SEED,
            "strategies": {
                "popularity": {
                    "description": "Training-window weighted views, cart additions, and completed purchases.",
                    "event_weights": EVENT_WEIGHTS,
                },
                "content": {
                    "description": "TF-IDF product text and metadata with cosine similarity to training-period interests.",
                    "features": [
                        "category",
                        "brand",
                        "description",
                        "price_band",
                    ],
                    "similarity": "cosine",
                },
                "hybrid": {
                    "description": "Weighted sum of independently max-normalized popularity and content scores.",
                    "default_weights": {
                        "popularity": 0.5,
                        "content": 0.5,
                    },
                    "formula": (
                        "score = w_pop * (popularity / max_popularity) + "
                        "w_content * (content_similarity / max_content_similarity)"
                    ),
                },
            },
            "cold_start": {
                "customer": "Fall back to training-window popularity when no training interactions exist.",
                "product": "Include eligible zero/low-interaction products; content similarity can rank them by catalog attributes.",
            },
            "training_data": list(TRAINING_FEATURE_SOURCES),
            "ground_truth_labels_are_model_inputs": False,
        }
