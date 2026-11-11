# Validation and anomaly handling

## What is validated

The application validator checks the generated dataset across these boundaries:

- Required fields, unique string IDs, foreign references and category hierarchy.
- Session/page-view chronology, cart and order lifecycle, line arithmetic and
  source-cart consistency.
- Cart/order lifecycle event sequences, allowed state transitions, nondecreasing
  timestamps, duplicate event IDs/sequences, entity references and final-state
  agreement.
- Chronological, non-overlapping train/validation/test windows and event counts.
- Held-out label provenance and split assignment; model runs must use the train
  split.
- Recommendation product availability, purchased-item exclusion and duplicate
  items.
- Isolated anomaly fixtures and intentional test-to-train leakage labels.

MongoDB JSON Schema validates individual document shapes. Cross-document
constraints remain application checks; the MongoDB schema does not pretend to
provide relational foreign keys.

## Append-only lifecycle history

The `lifecycle_events` collection records generated cart and order creation and
each status transition. Events contain entity type/ID, previous/new state,
event type, occurrence time, per-entity sequence and source/reference
information. Unique entity/sequence indexes prevent duplicate transitions.

Valid cart transitions are `active` → `converted`, `abandoned` or `cancelled`.
Valid order transitions are `pending` → `paid` or `cancelled`, `paid` →
`completed` or `refunded`, and `completed` → `refunded`. Terminal states do
not transition again. Historical rows are inserted, not replaced. Existing
legacy cart/order documents without event rows remain usable; validation does
not invent history that the old records did not preserve.

## Controlled challenge anomalies

`--inject-anomalies` adds four labelled examples to `anomaly_fixtures`, not the
clean entity collections:

1. Purchase before a valid same-session product view.
2. Product references a missing category.
3. Test-period order is assigned to training.
4. Recommendation includes an unavailable/discontinued product.

Each fixture retains source record IDs, a stable anomaly ID and expected
`ground_truth_label`. The validator emits findings to `validation_issues` with
type, severity, run ID and source IDs. This expected label is separate from
model inputs and is used only to check anomaly detection/traceability.

## Run and inspect

Run the validator against the default namespace:

```powershell
.\.venv\Scripts\python.exe -m backend.app.validation.cli
```

For the isolated full-scale namespace, set `MONGODB_COLLECTION_PREFIX=full_`
in the process environment or root `.env` before starting the CLI. The validator
initializes missing schema/index definitions but never changes business
records. It writes issue CSV/JSONL and a JSON summary under
`validation-output/`. A summary with zero issues is a completed validation,
not a missing result.
