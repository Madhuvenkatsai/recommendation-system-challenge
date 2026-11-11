# Dashboard and FastAPI integration

## Frontend pages

The React + Vite dashboard is a single-page workspace with these views:

- **Dashboard:** exact MongoDB collection counts, latest persisted generation
  run, validation summary, strategy descriptions and stored evaluation rows.
- **Data generation:** fixed seed `20261022`, starter/full scale selection,
  optional isolated anomaly fixtures, job state, written-record count, and
  final generation manifest.
- **Product catalog:** paginated products, escaped text search, category/status
  filters, lifecycle dates and category names.
- **Recommendation explorer:** customer lookup, strategy/K selection,
  optional as-of time, ranked product scores and backend-provided explanations.
- **Validation:** start validation, severity/type summaries and paginated
  issue detail with entity, source-record, run and ground-truth traceability.
- **Evaluation:** strategy comparisons at K=5 and K=10 with sample counts,
  skipped users and metric availability.

All displayed counts and metrics come from API responses. An empty database
returns its actual zero counts; unavailable MongoDB results in an explicit API
error state. The recommendation API does not expose ground-truth labels or an
excluded-product list; the explorer describes the backend's purchase and
availability filters without claiming to show excluded records.

## API routes used

| Route | Purpose |
|---|---|
| `GET /api/v1/dashboard/overview` | Counts, latest run, validation summary, strategies and recent evaluations |
| `GET /api/v1/catalog/categories` | Category filters |
| `GET /api/v1/catalog/products` | Product search, filter and pagination |
| `GET /api/v1/customers` | Customer search for recommendation requests |
| `POST /api/v1/generation` | Start starter/full generation |
| `GET /api/v1/generation/configurations` | Backend-defined fixed seed and scale volumes |
| `GET /api/v1/generation/status` | Most recent process-local generation job |
| `GET /api/v1/generation/jobs/{job_id}` | Poll a generation job |
| `POST /api/v1/validation` | Validate a selected or latest completed run |
| `GET /api/v1/validation/summary` | Latest/selected validation summary |
| `GET /api/v1/validation/issues` | Filter and page through persisted issues |
| `GET /api/v1/validation/status` | Most recent process-local validation job |
| `GET /api/v1/validation/jobs/{job_id}` | Poll a validation job |
| `POST, GET /api/v1/recommendations/customers/{customer_id}` | Generate/retrieve recommendations |
| `POST, GET /api/v1/recommendations/evaluations` | Run/retrieve held-out evaluation |
| `GET /api/v1/recommendations/strategies` | Strategy, model version and feature information |

The frontend API client uses `VITE_API_BASE_URL`; its local default is
`http://127.0.0.1:8000`. FastAPI CORS is restricted to `localhost` and
`127.0.0.1` on Vite's development (5173) and preview (4173) ports, without
credential cookies.

## Operation and database limitations

Generation and validation run through FastAPI background tasks and the
existing generator/validator implementations. Progress reports only completed
write batches; no percentage is invented. API generation start uses an atomic
MongoDB lease record to prevent two API workers from generating concurrently;
the lease is renewed as write batches complete and expires after process
failure. Job status is still stored in memory in one API process, so job
history and in-progress status do not survive a restart, and multiple workers
do not share the job registry.

Generation does not delete or replace documents. It refuses to start when the
deterministic run already exists or any guarded dataset collection is
populated. A failed generation can leave partial writes; those are not
automatically deleted and must be investigated before retrying. Validation
summaries are stored on their generation-run document, including zero-issue
reports, while API validation exports use a run-specific directory. MongoDB
configuration and reachability are required for all database-backed pages and
operations. This workspace has not been verified against a live MongoDB
server.
