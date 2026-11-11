from dataclasses import dataclass, field
from math import log2
from typing import Any, Iterable, Mapping


@dataclass
class RankingMetrics:
    k: int
    eligible_catalog_ids: set[str]
    cold_start_catalog_ids: set[str]
    evaluable_users: int = 0
    skipped_users: int = 0
    test_label_count: int = 0
    relevant_item_count: int = 0
    hit_count: int = 0
    hit_users: int = 0
    dcg_sum: float = 0.0
    ideal_dcg_sum: float = 0.0
    recommended_ids: set[str] = field(default_factory=set)
    recommended_cold_start_ids: set[str] = field(default_factory=set)
    recommendation_count: int = 0

    def add_user(
        self,
        recommendations: Iterable[str],
        relevant_products: Iterable[str],
        *,
        source_label_count: int | None = None,
    ) -> None:
        relevant = set(relevant_products) & self.eligible_catalog_ids
        self.test_label_count += (
            source_label_count if source_label_count is not None else len(relevant)
        )
        if not relevant:
            self.skipped_users += 1
            return
        ranked = list(recommendations)[: self.k]
        self.evaluable_users += 1
        self.relevant_item_count += len(relevant)
        self.recommendation_count += len(ranked)
        self.recommended_ids.update(ranked)
        self.recommended_cold_start_ids.update(
            product_id
            for product_id in ranked
            if product_id in self.cold_start_catalog_ids
        )
        hits = 0
        dcg = 0.0
        for rank, product_id in enumerate(ranked, start=1):
            if product_id in relevant:
                hits += 1
                dcg += 1.0 / log2(rank + 1)
        ideal_count = min(self.k, len(relevant))
        ideal_dcg = sum(1.0 / log2(rank + 1) for rank in range(1, ideal_count + 1))
        self.hit_count += hits
        self.hit_users += int(hits > 0)
        self.dcg_sum += dcg
        self.ideal_dcg_sum += ideal_dcg

    def as_metrics(self) -> dict[str, Any]:
        has_evaluable_users = self.evaluable_users > 0
        precision_denominator = self.evaluable_users * self.k
        catalog_denominator = len(self.eligible_catalog_ids)
        cold_denominator = len(self.cold_start_catalog_ids)
        return {
            "precision_at_k": (
                self.hit_count / precision_denominator
                if precision_denominator
                else None
            ),
            "recall_at_k": (
                self.hit_count / self.relevant_item_count
                if self.relevant_item_count
                else None
            ),
            "ndcg_at_k": (
                self.dcg_sum / self.ideal_dcg_sum
                if self.ideal_dcg_sum
                else None
            ),
            "hit_rate_at_k": (
                self.hit_users / self.evaluable_users
                if has_evaluable_users
                else None
            ),
            "catalog_coverage": (
                len(self.recommended_ids) / catalog_denominator
                if has_evaluable_users and catalog_denominator
                else None
            ),
            "cold_start_coverage": (
                len(self.recommended_cold_start_ids) / cold_denominator
                if has_evaluable_users and cold_denominator
                else None
            ),
            "evaluation_status": (
                "completed" if has_evaluable_users else "insufficient_test_data"
            ),
            "k": self.k,
            "evaluable_user_count": self.evaluable_users,
            "skipped_user_count": self.skipped_users,
            "test_label_count": self.test_label_count,
            "relevant_user_item_count": self.relevant_item_count,
            "hit_count": self.hit_count,
            "precision_denominator": precision_denominator,
            "recall_denominator": self.relevant_item_count,
            "ndcg_denominator": self.ideal_dcg_sum,
            "hit_rate_denominator": self.evaluable_users,
            "recommendation_count": self.recommendation_count,
            "catalog_coverage_numerator": len(self.recommended_ids),
            "catalog_coverage_denominator": catalog_denominator,
            "cold_start_coverage_numerator": len(
                self.recommended_cold_start_ids
            ),
            "cold_start_coverage_denominator": cold_denominator,
        }


def calculate_metrics(
    recommendations_by_user: Mapping[str, Iterable[str]],
    relevant_by_user: Mapping[str, Iterable[str]],
    *,
    k: int,
    eligible_catalog_ids: Iterable[str],
    cold_start_catalog_ids: Iterable[str] = (),
) -> dict[str, Any]:
    if k < 1:
        raise ValueError("k must be at least one.")
    accumulator = RankingMetrics(
        k=k,
        eligible_catalog_ids=set(eligible_catalog_ids),
        cold_start_catalog_ids=set(cold_start_catalog_ids),
    )
    for customer_id, relevant in relevant_by_user.items():
        accumulator.add_user(
            recommendations_by_user.get(customer_id, ()),
            relevant,
        )
    return accumulator.as_metrics()
