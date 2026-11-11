# MongoDB collection relationships

MongoDB stores references as the target document's string `_id`. The
application validator will check reference existence and cross-document rules;
MongoDB's document validators cannot provide relational foreign-key
constraints. References are indexed for those validation and retrieval paths.

```text
customers 1 ── * sessions 1 ── * page_views * ── 1 products
    │                             │
    ├── * carts 1 ── * cart_lines ┘
    │       │
    │       └────────────── 0..1 orders 1 ── * order_lines * ── 1 products
    ├── * orders
    └── * recommendations * ── 0..1 model_runs

categories 1 ── * products
categories 0..1 ── parent category (self-reference)
products 1 ── * product_relations ── 1 products (source/target product)

generation_runs 1 ── * validation_issues
generation_runs 1 ── * anomaly_fixtures
anomaly_fixtures embeds isolated fixture records and source IDs
dataset version 1 ── 1 train split
dataset version 1 ── 1 validation split
dataset version 1 ── 1 test split
dataset_splits 1 ── * ground_truth_labels
model_runs 1 ── * evaluation_results * ── 1 dataset_splits
```

## Cardinality and consistency rules

- A customer may have zero or many sessions, carts, orders and recommendation
  records. Each session/cart/order/recommendation belongs to one customer.
- A session has zero or many page views. A page view belongs to one session,
  customer and product; its customer must match the session customer and its
  timestamp must be inside the session window.
- A cart has zero or many cart lines. Each cart line belongs to one cart and
  product; one product may appear at most once in a cart (unique
  `(cart_id, product_id)` index).
- An order has one or more order lines in valid production data; each order
  line belongs to one order and product. One product may appear at most once in
  an order (unique `(order_id, product_id)` index). An optional source cart
  may convert to an order; a cart cannot have multiple orders.
- A category may have zero or many products and may have zero or one parent
  category. A product has zero or one category to support the required missing
  category anomaly fixture.
- A product may be the source or target of many product relations. Directed
  `(source, target, type)` triples are unique and self-relations are rejected
  by application validation.
- A recommendation contains an ordered embedded list of product IDs. Serving
  logic validates that each referenced product exists and is eligible for the
  recommendation's as-of time.
- Each dataset version has one train, validation and test split. Their
  windows must be chronological, non-overlapping and use half-open boundaries.
  Purchase labels reference their held-out split and the source order line.
  Only completed orders form positive purchase labels; cancelled/refunded
  orders do not. Repeated purchases of the same product remain distinct labels
  by source event. A model run references its train split; an evaluation
  references a held-out split and the model run it scores.
- Ground-truth labels are stored only in `ground_truth_labels`. The
  `ModelInputRepositories` bundle intentionally omits that collection;
  `EvaluationRepositories` is the explicit label-access surface.
- Anomaly and validation collections are available through a separate
  validation repository bundle, not the model-input repository. Their
  `ground_truth_label` fields therefore cannot enter the model feature path
  accidentally.
- Generation/validation/evaluation records are audit metadata, not source
  events or model features.
- `anomaly_fixtures` stores altered fixture copies and their explicit labels
  separately; it never mutates or inserts into the clean entity collections.
  `validation_issues` records deterministic findings with source IDs and the
  generation-run ID.

## Index inventory

Every collection has MongoDB's automatic unique `_id_` index. Additional
indexes are declared in `backend.app.db.schema.INDEXES` and are ensured by the
database initializer:

- Customer active status; category unique slug and parent reference.
- Product category/status and status/availability; customer/timestamp session
  history; session/sequence page-view uniqueness and customer/product event
  timelines.
- Cart customer/time and session reference; unique cart/product lines.
- Order customer/time, cart reference and status/time; unique order/product
  lines.
- Unique directed product relation and reverse target lookup; recommendation
  customer/request time and model-run reference.
- Generation status/time; unique validation issue ID, run/severity and
  issue/entity; unique anomaly ID and run/type.
- Unique dataset-version/split name; unique source-event label reference plus
  split/customer/product/time and customer event-time lookup.
- Model dataset/time and training-split indexes; unique model/split/K
  evaluation results.

The unique order/cart-to-order lifecycle relationship is validated in
application code; nullable references are not made unique sparse indexes.
