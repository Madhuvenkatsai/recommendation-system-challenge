# Recommendation and evaluation rules

## Training inputs and temporal boundary

`RecommendationService` resolves the selected completed generation run and its
`train` split. The half-open training window is `[start_at, end_at)`, and both
bounds are applied to page views, cart-line additions and completed-order
lines. Its `end_at` is the model cutoff.
Cancelled and refunded orders are never purchase interactions. Validation and
test events, `ground_truth_labels`, and anomaly-fixture records are not model
inputs.

Popularity weights are fixed at **view = 1**, **cart addition = 3**, and
**completed purchase = 5**. Each item's weighted count is divided by the
maximum eligible-catalog count to produce a [0, 1] score.

## Strategies

- **Popularity** ranks products by normalized training-window interaction
  counts.
- **Content** builds a scikit-learn TF-IDF matrix from product name,
  description, category, brand, and deterministic price-band tokens. The
  vocabulary is fit on catalog records created before the training cutoff.
  Cosine similarity between training-history items and eligible products is
  aggregated using the interaction weights.
- **Hybrid** independently max-normalizes popularity and content scores and
  combines them:

  ```text
  score = w_pop * (popularity / max_popularity)
        + w_content * (content_similarity / max_content_similarity)
  ```

  Default weights are `w_pop = 0.5` and `w_content = 0.5`; they are normalized
  to sum to one. `RecommendationEngine` and `RecommendationService` accept
  alternate non-negative weights.

Ties are resolved by ascending product ID. A customer with no training
interactions falls back to training-window popularity. Products marked
`is_cold_start` or with fewer than two training interactions remain candidates
when otherwise eligible; content similarity can rank them from catalog data.

## Eligibility, traceability, and reproducibility

Candidate eligibility is evaluated at `as_of_time`:

- The product must have been created and available by that time.
- An `available_to` timestamp is an exclusive end-of-availability boundary.
- `unavailable` products are excluded. A product marked `discontinued` is
  considered historically available only before its recorded `available_to`;
  it is excluded at or after that time and when no end boundary exists.
- Products with status `active` still must satisfy their availability bounds.
- Completed purchases by the customer strictly before `as_of_time` are
  excluded. Cancelled and refunded orders are ignored for this rule.
- Results are unique by product.

Recommendation records preserve customer/session, request and as-of times,
training cutoff, strategy/version, generation/model-run IDs, bounded source
interaction IDs, item rank/score/reason, and per-item eligibility status.
Stable model and recommendation IDs plus deterministic ordering support
repeatable output. The top-level source list is bounded to the customer's 100
most recently read training interaction IDs; item-level content evidence is
bounded to 10 supporting interaction IDs.

## Test-period evaluation

Evaluation runs each strategy separately at the test split start time and
compares its recommendations only with purchase labels assigned to that
generation's `test` split. The held-out labels are queried only by the
evaluation repository after the model is loaded. They are never passed to
`RecommendationEngine`. Test labels whose products were unavailable at the
recommendation time or already purchased before that time do not count as
eligible relevance. Users with no eligible relevant items are reported as
skipped and excluded from ranking-metric denominators.

For `U` evaluable users, cutoff `K`, total hits `H`, and total eligible
user/product relevance pairs `R`:

| Metric | Definition / denominator |
|---|---|
| Precision@K | `H / (U * K)`; denominator is reported as `precision_denominator`. |
| Recall@K | `H / R` (micro-averaged); `R` is `recall_denominator`. |
| NDCG@K | Sum of binary-gain DCG divided by the sum of ideal DCG across evaluable users. |
| Hit Rate@K | Users with at least one hit divided by `U`. |
| Catalog coverage | Distinct recommended eligible products divided by the eligible catalog size at test start. |
| Cold-start coverage | Distinct recommended eligible cold-start products divided by the eligible cold-start catalog size at test start. |

`evaluation_results.metrics` contains metric values and denominators, eligible
and skipped-user counts, label and recommendation counts, plus
`evaluation_status`. If no user has eligible test relevance, ranking and
coverage metrics are `null` and status is `insufficient_test_data`; they are
not represented as successful zero scores. A missing cold-start catalog yields
`cold_start_coverage = null`.

## API

- `POST /api/v1/recommendations/customers/{customer_id}` generates and stores
  a recommendation for `popularity`, `content`, or `hybrid`.
- `GET /api/v1/recommendations/customers/{customer_id}` retrieves stored
  recommendations.
- `POST /api/v1/recommendations/evaluations` evaluates strategies at the
  requested K values (defaults to 5 and 10) and stores model/evaluation runs.
- `GET /api/v1/recommendations/evaluations` retrieves stored results.
- `GET /api/v1/recommendations/strategies` reports versions, weights, feature
  sources, and cold-start behavior.

The recommendation request API does not accept or return ground-truth labels.
MongoDB-backed endpoints require the caller-provided `MONGODB_URI`; unit tests
do not establish live MongoDB integration.
