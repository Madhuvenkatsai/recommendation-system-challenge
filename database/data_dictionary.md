# MongoDB data dictionary

## Conventions and validation boundary

- MongoDB collection validators require the listed required fields and enforce
  BSON types, enumerations, minimums and patterns where shown. Fields marked
  optional may be omitted; fields marked nullable may also be explicitly
  `null`.
- Every `_id` is a required, non-empty BSON string and is unique through
  MongoDB's built-in `_id_` index. References use the exact same string value
  as the referenced document's `_id`; repositories do not coerce IDs.
- The challenge requirements supplied so far do not specify literal ID
  prefixes or layouts. The generator therefore uses documented, stable
  collection prefixes and zero-padded numeric suffixes; validators preserve
  these strings without transforming them. See the ID format table below.
- `date` means BSON UTC datetime. `decimal` means BSON Decimal128 for exact
  currency storage. `number` is a non-negative integer, long, double or
  Decimal128. `metric` has the same numeric types and is constrained to [0, 1].
- MongoDB collection validators do not enforce foreign-key existence,
  cross-document chronology, lifecycle transitions, arithmetic across
  documents, or split isolation. Those are application-level validation rules
  for the validator/generator phases; the database does reject malformed
  individual documents.
- `additionalProperties` is enabled for forward-compatible metadata. Known
  fields remain type-checked.

## Generated ID formats

The challenge did not provide literal ID patterns. The generator uses the
following stable, human-readable patterns; numeric suffixes are 1-based, with
at least eight digits (and expand as needed for collection size). Dataset
split and run IDs use a stable dataset fingerprint rather than a numeric
sequence.

| Entity / collection | ID format |
|---|---|
| Customer / `customers` | `CUS########` |
| Product / `products` | `PRO########` |
| Category / `categories` | `CAT########` |
| Session / `sessions` | `SES########` |
| Page view / `page_views` | `PVW########` |
| Cart / `carts` | `CRT########` |
| Cart line / `cart_lines` | `CLN########` |
| Order / `orders` | `ORD########` |
| Order line / `order_lines` | `OLN########` |
| Product relation / `product_relations` | `REL########` |
| Recommendation / `recommendations` | `REC########` |
| Ground-truth label / `ground_truth_labels` | `GTL########` |
| Dataset split / `dataset_splits` | `SPL` + dataset fingerprint + split name |
| Generation run / `generation_runs` | `RUN` + dataset fingerprint |
| Validation issue / `validation_issues` | `ISS` + 32 uppercase hexadecimal characters |
| Anomaly fixture / `anomaly_fixtures` | `ANF` + dataset fingerprint + anomaly type |

The database schema requires non-empty string IDs but intentionally does not
restrict documents to this generator-specific convention.

## Core entity collections

### `customers`

| Field | BSON type | Required | Rule / relationship |
|---|---|---:|---|
| `_id` | string | Yes | Unique customer ID; non-empty. |
| `created_at`, `updated_at` | date | Yes | Customer lifecycle timestamps. |
| `segment`, `region` | string or null | No | Optional descriptors; non-empty when supplied. |
| `attributes` | object | Yes | Extensible synthetic customer attributes. |
| `is_active` | bool | Yes | Customer status flag. |

### `products`

| Field | BSON type | Required | Rule / relationship |
|---|---|---:|---|
| `_id` | string | Yes | Unique product ID; non-empty. |
| `category_id` | string or null | No | Reference to `categories._id`; null supports the required missing-category fixture. |
| `name` | string | Yes | Non-empty product name. |
| `description` | string | Yes | Product text; empty text is allowed. |
| `brand` | string or null | No | Non-empty when supplied. |
| `attributes` | object | Yes | Extensible content/features. |
| `price` | Decimal128 | Yes | Non-negative catalog price. |
| `currency` | string | Yes | Three uppercase ASCII letters. |
| `status` | string | Yes | `active`, `unavailable`, or `discontinued`. |
| `available_from`, `available_to` | date or null | No | Optional inclusive availability bounds; ordering is application-validated. |
| `is_cold_start` | bool | Yes | Marks a product with insufficient interaction history. |
| `created_at`, `updated_at` | date | Yes | Product lifecycle timestamps. |

### `categories`

| Field | BSON type | Required | Rule / relationship |
|---|---|---:|---|
| `_id` | string | Yes | Unique category ID; non-empty. |
| `name`, `slug` | string | Yes | Non-empty; `slug` has a unique index. |
| `parent_category_id` | string or null | No | Optional self-reference to `categories._id`. |
| `seasonal_tags` | array of strings | Yes | Seasonal/category tags. |
| `active_from`, `active_to` | date or null | No | Optional active window; ordering is application-validated. |
| `created_at`, `updated_at` | date | Yes | Category lifecycle timestamps. |

### `sessions`

| Field | BSON type | Required | Rule / relationship |
|---|---|---:|---|
| `_id` | string | Yes | Unique session ID; non-empty. |
| `customer_id` | string | Yes | Reference to `customers._id`. |
| `started_at` | date | Yes | Session start. |
| `ended_at` | date or null | No | If supplied, must not precede `started_at` (application rule). |
| `source`, `device` | string or null | No | Optional non-empty descriptors. |
| `is_bot`, `is_noisy` | bool | Yes | Explicit traffic quality flags. |

### `page_views`

| Field | BSON type | Required | Rule / relationship |
|---|---|---:|---|
| `_id` | string | Yes | Unique page-view ID; non-empty. |
| `session_id` | string | Yes | Reference to `sessions._id`. |
| `customer_id` | string | Yes | Reference to `customers._id`; must agree with the session. |
| `product_id` | string | Yes | Reference to `products._id`. |
| `occurred_at` | date | Yes | Event timestamp; must fall within the session lifecycle. |
| `sequence` | int | Yes | Positive, 1-based position within its session. |
| `referrer` | string or null | No | Optional non-empty source. |

### `carts`

| Field | BSON type | Required | Rule / relationship |
|---|---|---:|---|
| `_id` | string | Yes | Unique cart ID; non-empty. |
| `customer_id` | string | Yes | Reference to `customers._id`. |
| `session_id` | string or null | No | Optional reference to `sessions._id`. |
| `created_at`, `updated_at` | date | Yes | Cart lifecycle timestamps; updated time cannot precede creation. |
| `converted_at` | date or null | No | Conversion time; required by application rules for converted carts. |
| `status` | string | Yes | `active`, `converted`, `abandoned`, or `cancelled`. |

### `cart_lines`

| Field | BSON type | Required | Rule / relationship |
|---|---|---:|---|
| `_id` | string | Yes | Unique cart-line ID; non-empty. |
| `cart_id` | string | Yes | Reference to `carts._id`. |
| `product_id` | string | Yes | Reference to `products._id`. |
| `quantity` | int | Yes | At least 1. |
| `unit_price`, `line_total` | Decimal128 | Yes | Non-negative price snapshot and line amount; `line_total = quantity × unit_price` (application-validated). |
| `added_at` | date | Yes | Must fall within the cart lifecycle (application-validated). |

### `orders`

| Field | BSON type | Required | Rule / relationship |
|---|---|---:|---|
| `_id` | string | Yes | Unique order ID; non-empty. |
| `customer_id` | string | Yes | Reference to `customers._id`. |
| `session_id`, `cart_id` | string or null | No | Optional references to `sessions._id` and `carts._id`. |
| `placed_at` | date | Yes | Order placement timestamp. |
| `status` | string | Yes | `pending`, `paid`, `completed`, `cancelled`, or `refunded`. |
| `currency` | string | Yes | Three uppercase ASCII letters. |
| `subtotal`, `discount_total`, `tax_total`, `shipping_total`, `total` | Decimal128 | Yes | Non-negative monetary amounts; total arithmetic is application-validated. |

### `order_lines`

| Field | BSON type | Required | Rule / relationship |
|---|---|---:|---|
| `_id` | string | Yes | Unique order-line ID; non-empty. |
| `order_id` | string | Yes | Reference to `orders._id`. |
| `product_id` | string | Yes | Reference to `products._id`. |
| `quantity` | int | Yes | At least 1. |
| `unit_price`, `discount`, `line_total` | Decimal128 | Yes | Non-negative price/discount snapshots and line amount; arithmetic is application-validated. |

### `product_relations`

| Field | BSON type | Required | Rule / relationship |
|---|---|---:|---|
| `_id` | string | Yes | Unique relation ID; non-empty. |
| `source_product_id`, `target_product_id` | string | Yes | References to `products._id`; self-links are application-rejected. |
| `relation_type` | string | Yes | `similar`, `complementary`, `substitute`, or `co_viewed`. |
| `weight` | number | Yes | Non-negative relation strength. |
| `created_at` | date | Yes | Relation creation timestamp. |

### `recommendations`

| Field | BSON type | Required | Rule / relationship |
|---|---|---:|---|
| `_id` | string | Yes | Unique recommendation-request/result ID; non-empty. |
| `customer_id` | string | Yes | Reference to `customers._id`. |
| `session_id` | string or null | No | Optional reference to the requesting `sessions._id`. |
| `model_run_id`, `generation_run_id` | string or null | No | Optional references to `model_runs._id` and `generation_runs._id`. |
| `strategy` | string | Yes | `popularity`, `content`, or `hybrid`. |
| `k` | int | Yes | Requested maximum recommendation count. |
| `model_version` | string | Yes | Recommendation implementation version. |
| `source_interaction_ids` | array of strings | Yes | Capped supporting training interactions used for traceability. |
| `requested_at`, `as_of_time` | date | Yes | Request and decision timestamps; recommendation rules use `as_of_time`. |
| `training_cutoff` | date or null | No | Optional model cutoff; cannot be later than `as_of_time` (application-validated). |
| `purchased_exclusion_rule` | string | Yes | Non-empty description/version of the applied exclusion rule. |
| `status` | string | Yes | `valid` or `anomaly_fixture`; serving code must emit only valid, eligible items. |
| `items` | array of objects | Yes | Each item requires non-empty `product_id`, positive integer `rank`, and numeric `score`; emitted items also include `reason`, supporting `source_interaction_ids` and `eligibility_status`. Unique ranks and product eligibility are application-validated. |

## Supporting collections

### `generation_runs`

| Field | BSON type | Required | Rule / relationship |
|---|---|---:|---|
| `_id` | string | Yes | Unique run ID; non-empty. |
| `seed` | long | Yes | Non-negative deterministic seed. |
| `configuration` | object | Yes | Generation configuration snapshot. |
| `status` | string | Yes | `pending`, `running`, `completed`, `failed`, or `interrupted`. |
| `started_at` | date | Yes | Run start. |
| `completed_at` | date or null | No | Run completion time. |
| `collection_counts`, `checksums` | object | Yes | Per-collection run manifest data. |
| `error` | string or null | No | Optional non-empty failure detail. |
| `validation_summary` | object | No | Persisted latest validation report for this generation run; present after validation completes, including clean zero-issue results. |
| `expires_at` | date | No | Temporary lease deadline for the API generation lock record; lock records are not completed data runs. |
| `lock_token` | string | No | Owning API job identifier for the generation lease. |

### `validation_issues`

| Field | BSON type | Required | Rule / relationship |
|---|---|---:|---|
| `_id`, `issue_id` | string | Yes | Same deterministic unique issue identifier. |
| `issue_type` | string | Yes | Machine-readable validation rule/anomaly type. |
| `severity` | string | Yes | `info`, `warning`, `error`, or `critical`. |
| `entity_type` | string | Yes | Affected collection/entity name. |
| `entity_id` | string or null | Yes | Affected entity ID, or null when unavailable. |
| `source_record_ids` | array of strings | Yes | IDs supporting this finding. |
| `generation_run_id` | string | Yes | Run whose data was validated. |
| `detected_at` | date | Yes | Deterministic validation timestamp for generated data. |
| `description` | string | Yes | Human-readable explanation of the violation. |
| `ground_truth_label` | string | Yes | Label used to score anomaly detection. |

### `anomaly_fixtures`

| Field | BSON type | Required | Rule / relationship |
|---|---|---:|---|
| `_id`, `anomaly_id` | string | Yes | Stable fixture ID and explicit anomaly identity. |
| `issue_type` | string | Yes | One of the four challenge anomaly types. |
| `severity` | string | Yes | `warning`, `error`, or `critical`. |
| `entity_type`, `entity_id` | string | Yes | Anomalous entity represented by embedded fixture data. |
| `source_record_ids` | array of strings | Yes | Clean records used to construct the isolated fixture. |
| `generation_run_id` | string | Yes | Generation run that created the fixture. |
| `detected_at` | date | Yes | Deterministic fixture timestamp. |
| `description`, `ground_truth_label` | string | Yes | Explanation and expected anomaly label. |
| `fixture_records` | array of objects | Yes | `{collection, document}` payloads; leakage records may also have `assigned_split_id`. Fixture documents are never written into clean entity collections. |

### `dataset_splits`

| Field | BSON type | Required | Rule / relationship |
|---|---|---:|---|
| `_id` | string | Yes | Unique split ID. |
| `dataset_version` | string | Yes | Non-empty dataset snapshot/version. |
| `split_name` | string | Yes | `train`, `validation`, or `test`. |
| `start_at`, `end_at` | date | Yes | Half-open chronological window `[start_at, end_at)`; must have positive duration. |
| `created_at` | date | Yes | Split-definition timestamp. |
| `event_count` | int | Yes | Non-negative count. |

### `ground_truth_labels`

| Field | BSON type | Required | Rule / relationship |
|---|---|---:|---|
| `_id` | string | Yes | Unique label ID. |
| `customer_id`, `product_id` | string | Yes | References to `customers._id` and `products._id`. |
| `source_event_id` | string | Yes | Unique source `order_lines._id`; traceable outcome event. |
| `dataset_split_id` | string | Yes | Reference to `dataset_splits._id`; held-out labels are stored here, not in model feature collections. |
| `event_type` | string | Yes | `purchase`, `view`, or `cart`. |
| `occurred_at` | date | Yes | Label event timestamp, inside its split window. |
| `relevance` | number | Yes | Non-negative relevance value. |

### `model_runs`

| Field | BSON type | Required | Rule / relationship |
|---|---|---:|---|
| `_id` | string | Yes | Unique model-run ID. |
| `algorithm`, `model_version`, `dataset_version` | string | Yes | Non-empty model and dataset identifiers. |
| `training_split_id` | string | Yes | Reference to a `dataset_splits` train record. |
| `training_cutoff` | date | Yes | Must not exceed the training window's end or include later source events. |
| `parameters` | object | Yes | Model parameters/configuration. |
| `feature_sources` | array of strings | Yes | Source collection names; must not contain `ground_truth_labels`. |
| `status` | string | Yes | `pending`, `running`, `completed`, or `failed`. |
| `created_at` | date | Yes | Run creation time. |
| `completed_at` | date or null | No | Completion time when available. |

### `evaluation_results`

| Field | BSON type | Required | Rule / relationship |
|---|---|---:|---|
| `_id` | string | Yes | Unique evaluation-result ID. |
| `model_run_id` | string | Yes | Reference to `model_runs._id`. |
| `dataset_split_id` | string | Yes | Reference to validation/test `dataset_splits._id`. |
| `k` | int | Yes | Positive ranking cutoff. |
| `evaluated_at` | date | Yes | Evaluation timestamp. |
| `sample_count` | int | Yes | Non-negative evaluation sample count. |
| `metrics` | object | Yes | Requires `precision_at_k`, `recall_at_k`, `ndcg_at_k`, `hit_rate_at_k`, `catalog_coverage`, and `cold_start_coverage`; values are numeric in [0, 1] or null when the denominator is unavailable. Also records sample counts, denominators and evaluation status. |
