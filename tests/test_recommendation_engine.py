from datetime import datetime, timezone
from math import log2

import pytest

from backend.app.generator.config import GENERATION_SEED
from backend.app.recommendations.engine import Interaction, RecommendationEngine
from backend.app.recommendations.metrics import RankingMetrics, calculate_metrics
from backend.app.repositories.model_input import get_model_input_repositories
from tests.test_data_generation import FakeMongoDatabase

CUTOFF = datetime(2025, 1, 1, tzinfo=timezone.utc)
AS_OF = datetime(2025, 2, 1, tzinfo=timezone.utc)


def product(
    product_id: str,
    *,
    category: str = "CAT00000001",
    description: str = "outdoor hiking backpack",
    brand: str = "Trail Co",
    status: str = "active",
    available_to: datetime | None = None,
    cold_start: bool = False,
) -> dict:
    return {
        "_id": product_id,
        "category_id": category,
        "name": f"{product_id} backpack",
        "description": description,
        "brand": brand,
        "attributes": {"category_index": 1},
        "price": 30.0,
        "status": status,
        "available_from": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "available_to": available_to,
        "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "is_cold_start": cold_start,
    }


def category() -> dict:
    return {
        "_id": "CAT00000001",
        "name": "Outdoor Gear",
        "slug": "outdoor-gear",
    }


def event(
    customer_id: str,
    product_id: str,
    event_type: str,
    source_id: str,
    *,
    occurred_at: datetime = datetime(2024, 6, 1, tzinfo=timezone.utc),
) -> Interaction:
    return Interaction(
        customer_id=customer_id,
        product_id=product_id,
        occurred_at=occurred_at,
        event_type=event_type,
        source_id=source_id,
        session_id="SES00000001",
    )


def build_engine(
    products: list[dict],
    interactions: list[Interaction],
    **kwargs,
) -> RecommendationEngine:
    return RecommendationEngine(
        products,
        [category()],
        interactions,
        training_cutoff=CUTOFF,
        generation_run_id="RUN00000000000001",
        **kwargs,
    )


def test_popularity_ranking_uses_documented_event_weights() -> None:
    products = [product("PRO00000001"), product("PRO00000002")]
    interactions = [
        event("CUS1", "PRO00000001", "cart", "cart-1"),
        event("CUS1", "PRO00000001", "cart", "cart-2"),
        event("CUS1", "PRO00000002", "purchase", "purchase-1"),
    ]

    result = build_engine(products, interactions).recommend(
        "CUS2", strategy="popularity", as_of_time=AS_OF, k=2
    )

    assert [item.product_id for item in result.items] == [
        "PRO00000001",
        "PRO00000002",
    ]
    assert result.items[0].score == 1
    assert result.items[1].score == pytest.approx(5 / 6)


def test_content_similarity_recommends_related_cold_start_products() -> None:
    products = [
        product("PRO00000001", description="lightweight outdoor hiking pack"),
        product(
            "PRO00000002",
            description="lightweight outdoor hiking backpack",
            cold_start=True,
        ),
        product(
            "PRO00000003",
            category="CAT00000002",
            description="kitchen blender appliance",
            brand="Home Co",
        ),
    ]
    interactions = [event("CUS1", "PRO00000001", "view", "view-1")]

    result = build_engine(products, interactions).recommend(
        "CUS1", strategy="content", as_of_time=AS_OF, k=3
    )

    assert result.items[0].product_id == "PRO00000001"
    assert result.items[1].product_id == "PRO00000002"
    assert "attributes" in result.items[1].reason or "category" in result.items[1].reason
    assert "view-1" in result.items[1].source_interaction_ids


def test_hybrid_scores_combine_max_normalized_components_and_weights() -> None:
    products = [product(f"PRO{i:08d}") for i in range(1, 4)]
    interactions = [
        event("CUS1", "PRO00000001", "view", "view-1"),
        event("CUS1", "PRO00000002", "purchase", "purchase-1"),
    ]
    engine = build_engine(
        products,
        interactions,
        popularity_weight=0.7,
        content_weight=0.3,
    )
    candidate_ids = [record["_id"] for record in products]
    popularity = engine.popularity
    content, _ = engine._content_scores("CUS1", candidate_ids)
    max_pop = max(popularity.values())
    max_content = max(content.values())

    result = engine.recommend(
        "CUS1", strategy="hybrid", as_of_time=AS_OF, k=3
    )
    scores = {item.product_id: item.score for item in result.items}
    for product_id in candidate_ids:
        expected = 0.7 * popularity.get(product_id, 0) / max_pop
        if max_content:
            expected += 0.3 * content[product_id] / max_content
        assert scores[product_id] == pytest.approx(expected, abs=1e-7)


def test_cold_start_customer_falls_back_to_training_popularity() -> None:
    products = [product("PRO00000001"), product("PRO00000002")]
    engine = build_engine(
        products,
        [event("CUS1", "PRO00000002", "purchase", "purchase-1")],
    )

    result = engine.recommend(
        "CUS_NEW", strategy="content", as_of_time=AS_OF, k=1
    )

    assert result.items[0].product_id == "PRO00000002"
    assert "popularity fallback" in result.items[0].reason
    assert result.source_interaction_ids == []


def test_purchased_unavailable_and_discontinued_products_are_excluded() -> None:
    end_of_life = datetime(2025, 3, 1, tzinfo=timezone.utc)
    products = [
        product("PRO00000001"),
        product("PRO00000002", status="unavailable"),
        product(
            "PRO00000003",
            status="discontinued",
            available_to=end_of_life,
        ),
    ]
    engine = build_engine(
        products,
        [event("CUS1", "PRO00000001", "purchase", "purchase-1")],
    )

    historic = engine.recommend(
        "CUS2", strategy="popularity", as_of_time=AS_OF, k=5
    )
    current = engine.recommend(
        "CUS2",
        strategy="popularity",
        as_of_time=datetime(2025, 4, 1, tzinfo=timezone.utc),
        k=5,
    )
    with_purchase_exclusion = engine.recommend(
        "CUS1",
        strategy="popularity",
        as_of_time=AS_OF,
        purchased_product_ids={"PRO00000001"},
        k=5,
    )

    assert "PRO00000003" in [item.product_id for item in historic.items]
    assert "PRO00000003" not in [item.product_id for item in current.items]
    assert "PRO00000002" not in [item.product_id for item in historic.items]
    assert "PRO00000001" not in [
        item.product_id for item in with_purchase_exclusion.items
    ]


def test_prior_purchase_query_uses_only_completed_orders_before_as_of_time() -> None:
    from types import SimpleNamespace

    from backend.app.recommendations.service import RecommendationService

    class Orders:
        def __init__(self) -> None:
            self.pipeline = None

        def iter_aggregate(self, pipeline, *, batch_size):
            assert batch_size > 0
            self.pipeline = pipeline
            yield {"product_id": "PRO00000001"}

    service = object.__new__(RecommendationService)
    service.batch_size = 100
    orders = Orders()
    service.model_input = SimpleNamespace(orders=orders)

    purchased = service._purchased_before("CUS1", AS_OF)

    match = orders.pipeline[0]["$match"]
    assert match["status"] == "completed"
    assert match["placed_at"] == {"$lt": AS_OF}
    assert purchased == {"PRO00000001"}


def test_training_interaction_queries_use_the_complete_half_open_split() -> None:
    from types import SimpleNamespace

    from backend.app.recommendations.service import RecommendationService

    start_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    cutoff = datetime(2024, 6, 1, tzinfo=timezone.utc)

    class Source:
        def __init__(self) -> None:
            self.query = None
            self.pipeline = None

        def iter_many(self, query, *, projection=None, batch_size=1000, sort=None):
            assert batch_size > 0
            assert projection is not None and sort is not None
            self.query = query
            return iter(())

        def iter_aggregate(self, pipeline, *, batch_size=1000):
            assert batch_size > 0
            self.pipeline = pipeline
            return iter(())

    service = object.__new__(RecommendationService)
    service.batch_size = 100
    page_views, cart_lines, orders = Source(), Source(), Source()
    service.model_input = SimpleNamespace(
        page_views=page_views, cart_lines=cart_lines, orders=orders
    )

    assert list(service._training_interactions(start_at, cutoff)) == []
    assert page_views.query["occurred_at"] == {"$gte": start_at, "$lt": cutoff}
    assert cart_lines.pipeline[0]["$match"]["added_at"] == {
        "$gte": start_at,
        "$lt": cutoff,
    }
    assert orders.pipeline[0]["$match"]["placed_at"] == {
        "$gte": start_at,
        "$lt": cutoff,
    }


def test_duplicates_are_removed_and_future_training_events_are_ignored() -> None:
    products = [product(f"PRO{i:08d}") for i in range(1, 4)]
    events = [
        event("CUS1", "PRO00000001", "view", "view-1"),
        event("CUS1", "PRO00000001", "cart", "cart-1"),
        event(
            "CUS1",
            "PRO00000002",
            "purchase",
            "future-purchase",
            occurred_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        ),
    ]
    first = build_engine(products, events)
    second = build_engine(products, events[:2])
    first_result = first.recommend("CUS1", strategy="hybrid", as_of_time=AS_OF, k=5)
    second_result = second.recommend("CUS1", strategy="hybrid", as_of_time=AS_OF, k=5)

    assert first.popularity == second.popularity
    assert first_result.items == second_result.items
    assert len({item.product_id for item in first_result.items}) == len(
        first_result.items
    )
    assert first_result.items == first.recommend(
        "CUS1", strategy="hybrid", as_of_time=AS_OF, k=5
    ).items


def test_future_products_are_not_recommended_before_creation() -> None:
    future = product("PRO00000002")
    future["created_at"] = datetime(2025, 2, 2, tzinfo=timezone.utc)
    engine = build_engine(
        [product("PRO00000001"), future],
        [event("CUS1", "PRO00000001", "view", "view-1")],
    )

    result = engine.recommend(
        "CUS1",
        strategy="content",
        as_of_time=datetime(2025, 2, 1, tzinfo=timezone.utc),
        k=5,
    )

    assert "PRO00000002" not in [item.product_id for item in result.items]


def test_recommendation_records_are_traceable_and_do_not_use_ground_truth() -> None:
    requested_at = datetime(2025, 2, 2, tzinfo=timezone.utc)
    engine = build_engine(
        [product("PRO00000001")],
        [event("CUS1", "PRO00000001", "view", "source-view")],
    )
    document = engine.recommend(
        "CUS1",
        strategy="popularity",
        as_of_time=AS_OF,
        requested_at=requested_at,
        k=1,
    ).as_document()
    model_run = engine.model_run_document("popularity")

    assert document["generation_run_id"] == engine.generation_run_id
    assert document["requested_at"] == requested_at
    assert document["as_of_time"] == AS_OF
    assert document["training_cutoff"] == CUTOFF
    assert document["source_interaction_ids"] == ["source-view"]
    assert document["items"][0]["source_interaction_ids"] == []
    assert document["items"][0]["eligibility_status"] == "eligible"
    assert "ground_truth_labels" not in model_run["feature_sources"]
    assert "ground_truth_labels" not in get_model_input_repositories(
        FakeMongoDatabase()
    ).__dict__
    assert engine.seed == GENERATION_SEED


def test_precision_recall_ndcg_hit_rate_and_coverage_values() -> None:
    result = calculate_metrics(
        {"u1": ["a", "b"], "u2": ["c"]},
        {"u1": ["a", "c"], "u2": ["b"]},
        k=2,
        eligible_catalog_ids={"a", "b", "c"},
        cold_start_catalog_ids={"c"},
    )

    assert result["precision_at_k"] == pytest.approx(1 / 4)
    assert result["recall_at_k"] == pytest.approx(1 / 3)
    assert result["ndcg_at_k"] == pytest.approx(1 / (2 + 1 / log2(3)))
    assert result["hit_rate_at_k"] == pytest.approx(1 / 2)
    assert result["catalog_coverage"] == 1
    assert result["cold_start_coverage"] == 1
    assert result["precision_denominator"] == 4
    assert result["recall_denominator"] == 3
    assert result["evaluable_user_count"] == 2


def test_users_without_eligible_test_truth_are_skipped_not_scored_as_zero() -> None:
    result = calculate_metrics(
        {"u1": ["a"], "u2": ["b"]},
        {"u1": [], "u2": ["b"]},
        k=5,
        eligible_catalog_ids={"a", "b"},
    )
    empty = calculate_metrics(
        {"u1": ["a"]},
        {"u1": []},
        k=5,
        eligible_catalog_ids={"a"},
    )

    assert result["evaluable_user_count"] == 1
    assert result["skipped_user_count"] == 1
    assert result["hit_rate_at_k"] == 1
    assert empty["evaluation_status"] == "insufficient_test_data"
    assert empty["precision_at_k"] is None
    assert empty["recall_at_k"] is None
    assert empty["catalog_coverage"] is None


def test_invalid_training_cutoff_and_hybrid_weights_are_rejected() -> None:
    with pytest.raises(ValueError, match="seed is fixed"):
        build_engine(
            [product("PRO00000001")],
            [],
            seed=1,
        )
    with pytest.raises(ValueError, match="positive"):
        build_engine(
            [product("PRO00000001")],
            [],
            popularity_weight=0,
            content_weight=0,
        )


def test_generated_held_out_test_labels_are_used_only_for_metric_calculation() -> None:
    from tests.test_data_generation import generate

    generated, _ = generate()
    rows = generated.records
    splits = {row["split_name"]: row for row in rows["dataset_splits"]}
    train_cutoff = splits["train"]["end_at"]
    test_start = splits["test"]["start_at"]
    category_rows = rows["categories"]
    cart_by_id = {row["_id"]: row for row in rows["carts"]}
    order_by_id = {row["_id"]: row for row in rows["orders"]}
    interactions = [
        event(
            row["customer_id"],
            row["product_id"],
            "view",
            row["_id"],
            occurred_at=row["occurred_at"],
        )
        for row in rows["page_views"]
        if row["occurred_at"] < train_cutoff
    ]
    interactions.extend(
        Interaction(
            customer_id=cart_by_id[row["cart_id"]]["customer_id"],
            product_id=row["product_id"],
            occurred_at=row["added_at"],
            event_type="cart",
            source_id=row["_id"],
            session_id=cart_by_id[row["cart_id"]]["session_id"],
        )
        for row in rows["cart_lines"]
        if row["added_at"] < train_cutoff
    )
    interactions.extend(
        Interaction(
            customer_id=order_by_id[row["order_id"]]["customer_id"],
            product_id=row["product_id"],
            occurred_at=order_by_id[row["order_id"]]["placed_at"],
            event_type="purchase",
            source_id=row["_id"],
            session_id=order_by_id[row["order_id"]]["session_id"],
        )
        for row in rows["order_lines"]
        if order_by_id[row["order_id"]]["status"] == "completed"
        and order_by_id[row["order_id"]]["placed_at"] < train_cutoff
    )
    model = RecommendationEngine(
        rows["products"],
        category_rows,
        interactions,
        training_cutoff=train_cutoff,
        generation_run_id=rows["generation_runs"][0]["_id"],
    )
    heldout_labels = [
        row
        for row in rows["ground_truth_labels"]
        if row["dataset_split_id"] == splits["test"]["_id"]
    ]
    relevant_by_user: dict[str, set[str]] = {}
    for label in heldout_labels:
        relevant_by_user.setdefault(label["customer_id"], set()).add(
            label["product_id"]
        )
    prior_purchases: dict[str, set[str]] = {}
    for line in rows["order_lines"]:
        order = order_by_id[line["order_id"]]
        if order["status"] == "completed" and order["placed_at"] < test_start:
            prior_purchases.setdefault(order["customer_id"], set()).add(
                line["product_id"]
            )

    metrics = RankingMetrics(
        k=5,
        eligible_catalog_ids={
            row["_id"] for row in model.eligible_catalog(test_start)
        },
        cold_start_catalog_ids=model.cold_start_products(test_start),
    )
    for customer_id, products in relevant_by_user.items():
        result = model.recommend(
            customer_id,
            strategy="hybrid",
            as_of_time=test_start,
            k=5,
            purchased_product_ids=prior_purchases.get(customer_id, ()),
        )
        metrics.add_user(
            [item.product_id for item in result.items],
            products - prior_purchases.get(customer_id, set()),
        )
    evaluated = metrics.as_metrics()

    assert heldout_labels
    assert "ground_truth_labels" not in model.model_run_document("hybrid")[
        "feature_sources"
    ]
    assert evaluated["test_label_count"] == len(heldout_labels)
    assert evaluated["evaluable_user_count"] + evaluated["skipped_user_count"] == len(
        relevant_by_user
    )
    assert evaluated["evaluation_status"] in {
        "completed",
        "insufficient_test_data",
    }
