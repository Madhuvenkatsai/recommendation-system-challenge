# Synthetic data generation rules

The generator is available as `backend.app.generator` and uses only Python's
standard library plus the project's existing PyMongo installation. It has no
local database or credential fallback.

## Run and database requirements

From `C:\CandidateWorkspace`, after providing `MONGODB_URI` (and optionally
`MONGODB_DATABASE`) in the PowerShell environment:

```powershell
.\.venv\Scripts\python.exe -m backend.app.generator.cli --scale starter
.\.venv\Scripts\python.exe -m backend.app.generator.cli --scale full
```

The CLI initializes/updates the declared MongoDB validators and indexes, then
generates in ordered batches. It inserts records; it does not delete or
overwrite existing documents. Run each dataset against empty generated
collections or a fresh database. A duplicate-key/server error is surfaced;
partial inserts from a failed run are not rolled back.

By default, CSV and JSON Lines exports plus `manifest.json` are written under
`generated-data/`. Use `--output-dir` and `--batch-size` to change the export
location or write batch bound. The manifest contains the collection row counts
and SHA-256 checksums. Checksums are over canonical, sorted-key JSON lines and
exclude `generation_runs`, whose timestamps intentionally record actual
execution time. Empty schema collections still receive empty export files.

The generator ID prefixes and layouts are documented in the
[data dictionary](../database/data_dictionary.md). They are stable for a
given scale/configuration and do not claim to implement an ID pattern that the
challenge statement did not specify.

## Scale settings

| Setting | Starter | Full |
|---|---:|---:|
| Customers | 200 | 20,000 |
| Products | 100 | 10,000 |
| Categories | 12 | 40 |
| Sessions | 2,500 | 500,000 |
| Orders | 500 | 100,000 |
| Carts | 1,250 | 250,000 |
| Page views | 1-5 per session; configured mean 3 | 1-5 per session; configured mean 3 |
| Cart lines | 1-3 per cart | 1-3 per cart |
| Order lines | same product/quantity snapshot as source cart | same product/quantity snapshot as source cart |

Seed `20261022` and the synthetic event window `[2024-01-01, 2026-01-01)` are
fixed. The generator rejects a different seed. Starter and full call the same
generation path; counts are configurable through `GenerationConfig` for small
tests, subject to valid relationships (orders <= carts <= sessions).

## Generation order and deterministic rules

1. Categories: eight seasonal roots followed by child categories. Children
   reference their root through `parent_category_id`; seasonal tags are
   inherited from their root.
2. Customers: 30% regular-activity tier and 70% sparse tier. Session assignment
   draws 90% of sessions from regular-tier customers and 10% across all
   customers, yielding many sparse and zero-session customers.
3. Products: category IDs round-robin across categories. The first 80% are
   popular active products used in interactions; the next 10% are active
   cold-start products with no generated views or purchases; the next 5% are
   unavailable; the remainder are discontinued with an end-of-life timestamp.
   Prices are deterministic USD cents and stored as Decimal128.
4. Sessions: IDs are ordered by `started_at`, spread over the synthetic
   timeline. Customer assignment and duration are seed-derived. Two percent
   are flagged as bots and five percent as noisy; bot/noisy events remain
   explicitly marked.
5. Page views: a deterministic session depth from one to five (configured
   arithmetic mean three), with positive sequence numbers and strictly
   increasing timestamps inside the session. Products are sampled without
   replacement from the popular catalog with deterministic quadratic
   weighting toward lower product indices.
6. Carts and cart lines: each cart maps to one session. Each contains one to
   three distinct products from that session's earlier page views. The
   configured cart count is `max(orders, sessions // 2)` unless explicitly
   set. Converted carts are spread evenly across the cart timeline, one per
   order; remaining carts are deterministically abandoned or active.
7. Orders and lines: one order for each converted cart, placed after its cart
   line additions and before the associated session ends. Order lines preserve
   cart product, quantity and unit-price snapshots. Status is deterministically
   assigned as 94% completed, 4% cancelled and 2% refunded. Subtotal is the
   line sum; discount is zero; tax is rounded 10%; shipping is $5 below a
   $100 subtotal and free otherwise; total is their sum.
8. Product relations: each active product receives one `similar` relation to
   the next active product in the same category, and one `complementary`
   relation to the first product in a deterministic sibling/child category.
   Similar/complementary weights are fixed at 1.0/0.5. Relation existence is
   rule-derived, not sampled independently.
9. Dataset splits: three non-overlapping chronological windows over the fixed
   timeline, 70% train, 15% validation, 15% test. `event_count` counts
   page-view, cart-creation and order events falling within each half-open
   window.
10. Ground-truth labels: every order line from a completed order in
    validation/test becomes a separate purchase label referencing its source
    order-line ID and split. Cancelled/refunded orders are not positive
    purchase outcomes. Training outcomes remain source interaction data and
    are not copied as evaluation labels. Model fitting must filter source
    events at the train cutoff; `ground_truth_labels` is not present on the
    model-input repository bundle.
11. Optional anomaly fixtures are written separately after baseline and
    ground-truth records. A completed `generation_runs` manifest record is
    written last. No production recommendations, model runs, validation
    issues or evaluation results are generated by the data generator; they are
    downstream products, not fabricated outcomes.

## Reproducibility and boundaries

Each dataset row is built from its collection ordinal, fixed seed and config;
the generator uses bounded batches and does not retain full event collections
in memory. Small category/product metadata and per-session view samples are
derived on demand. Re-running the same config yields the same deterministic
dataset checksums and row counts. Execution timestamps in the run audit record
are intentionally not deterministic and are excluded from dataset checksums.

The clean baseline does not inject the four required anomaly fixtures. MongoDB
enforces document-level schemas. Anomaly injection is an independent optional
stage:

```powershell
.\.venv\Scripts\python.exe -m backend.app.generator.cli --scale starter --inject-anomalies
```

`--anomaly-types` can select any subset of the four fixture types. Fixtures
include stable anomaly IDs, issue type, severity, ground-truth label, source
record IDs and generation-run ID. The altered order/product/recommendation
documents are embedded in `anomaly_fixtures`; clean entity collections are
never edited. The leakage fixture associates a test-period order with the
train split explicitly.

The application validator is run against the configured MongoDB database:

```powershell
.\.venv\Scripts\python.exe -m backend.app.validation.cli
.\.venv\Scripts\python.exe -m backend.app.validation.cli --generation-run-id RUN...
```

It checks primary-key uniqueness and required fields; foreign references and
category hierarchy; session, view, cart and order chronology; cart/order
arithmetic and lifecycle; product availability and recommendation eligibility;
chronological split windows, held-out labels and deliberate train/test leakage;
and duplicate events. Findings are written in bounded batches to
`validation_issues` and to `validation-output/validation_issues.csv`,
`validation-output/validation_issues.jsonl`, and
`validation-output/validation_summary.json`. Summary counts include issue types,
severities, clean core-entity rows and embedded anomalous fixture rows.
Validation indexes relationship metadata rather than retaining source
documents; issue writes and exports are bounded by `--batch-size`.

Validation timestamps, issue IDs and anomaly fixtures are deterministic for a
given generated run. The issue export identifies `ground_truth_label` and
`source_record_ids`, keeping the expected anomaly label explicit and auditable.
The clean baseline remains independently reproducible when fixtures are
disabled. MongoDB batch writes and indexes require a real configured MongoDB
instance; unit tests do not represent a live database integration run.
