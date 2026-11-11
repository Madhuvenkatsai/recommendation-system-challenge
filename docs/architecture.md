# Project architecture

- `frontend/`: React + Vite dashboard client. It does not connect to MongoDB.
- `backend/`: FastAPI application, MongoDB configuration and PyMongo repository
  boundaries.
- `database/`: MongoDB data dictionary, collection relationships and schema
  setup documentation.
- `tests/`: backend health, schema-definition, initialization and repository
  boundary tests.

MongoDB configuration is supplied through `MONGODB_URI` and
`MONGODB_DATABASE`; no credentials or fallback database are provided. The API
can start without MongoDB configured. `GET /health` checks API liveness;
`GET /api/v1/health` pings MongoDB and reports an explicit 503 status when it
is missing or unavailable.

`backend.app.db.schema` defines validators and indexes for all 11 core entity
collections and seven supporting collections. Run
`python -m backend.app.db.initialize` from the workspace root with a supplied
MongoDB connection to create/update the schema. Initialization creates no
application documents. Collection and field details are in the
[data dictionary](../database/data_dictionary.md) and
[relationship guide](../database/relationships.md).

Model-input repositories intentionally do not expose `ground_truth_labels`,
`validation_issues` or `anomaly_fixtures`; labels are available through the
separate evaluation repository bundle, and anomaly/validation data through
the validation repository bundle. MongoDB validators enforce document-level
shapes, while reference existence, lifecycle, arithmetic and temporal/split
invariants require application-level validation.

The fixed-seed generator streams source records through bounded MongoDB and
export targets. Chronological split records are derived from event timestamps;
completed validation/test order lines are separately copied into
`ground_truth_labels`; recommendation, model and evaluation result documents
are not synthesized by the generator. See the [generation rules](data_generation.md).

Controlled anomaly fixtures are optional and are persisted in
`anomaly_fixtures`, separate from the reproducible clean baseline. The
`backend.app.validation` engine streams findings in bounded batches to
`validation_issues` and issue-level CSV/JSONL plus summary exports. It checks
references, hierarchy, chronology, arithmetic, lifecycle, split isolation,
recommendation eligibility and duplicate events. The repository has unit
coverage for these paths; live MongoDB reads/writes require a supplied,
reachable MongoDB connection.

The recommendation engine uses training-window-only weighted interaction
popularity and scikit-learn TF-IDF/cosine content similarity, with a configurable
normalized hybrid strategy. The API creates traceable recommendation and model
records; evaluation reads only test-split purchase labels through the separate
evaluation repository and stores per-strategy, per-K results. See the
[recommendation and evaluation rules](recommendations.md).

The Phase 5 dashboard consumes FastAPI endpoints for MongoDB-backed overview,
catalog, customer search, generation jobs and validation summaries/issues,
alongside the recommendation and evaluation routes above. CORS allows only
localhost/127.0.0.1 Vite development and preview origins. Generation and
validation use the existing bounded engines and targets; operation status is
process-local and is not durable across API restarts. Data generation refuses
to write into collections that already contain records rather than silently
overwriting them. See the [frontend integration notes](frontend.md).
