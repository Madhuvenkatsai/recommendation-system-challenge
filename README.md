# E-commerce Product Recommendation System

The project has separate React + Vite frontend, FastAPI backend, and MongoDB
database layers. MongoDB schemas and indexes are initialized by an idempotent
script. A deterministic synthetic data generator supports starter/full scales,
optional isolated anomaly fixtures, MongoDB writes and CSV/JSONL exports. An
application validator exports traceable validation issues and summaries. The
FastAPI recommendation API implements popularity, content-based and hybrid
recommendation strategies plus test-split evaluation metrics.

## Prerequisites

- Python 3.11+
- Node.js 20.19+ or 22.12+
- A MongoDB instance and a connection string when database-backed features are
  needed

The API can start without MongoDB configured. Its liveness route will respond,
while the MongoDB health route reports `not_configured`. MongoDB is never
silently replaced with another database.

## Backend

From the workspace root, create and activate a virtual environment, then
install backend dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements-dev.txt
```

Set `MONGODB_URI` to a connection string supplied for your MongoDB instance.
Optionally set `MONGODB_DATABASE` (defaults to `product_recommendations`).
`.env.example` documents the variables but is not loaded automatically; do not
put real credentials in tracked files.

Start the API from the workspace root:

```powershell
python -m uvicorn backend.app.main:app --reload
```

- `GET http://127.0.0.1:8000/health` checks API liveness.
- `GET http://127.0.0.1:8000/api/v1/health` pings MongoDB and returns HTTP 503
  with an explicit reason when it is not configured or unavailable.

## MongoDB schema initialization

After MongoDB is available and `MONGODB_URI` is set in the current shell,
initialize the collections and indexes from the workspace root:

```powershell
.\.venv\Scripts\python.exe -m backend.app.db.initialize
```

This idempotently creates/updates collection validators and indexes. It does
not insert or generate data. See the [database setup and schema
documentation](database/README.md), [data dictionary](database/data_dictionary.md),
and [collection relationships](database/relationships.md).

## Synthetic data generation

Generation requires a configured, reachable MongoDB instance and writes
batches to the configured MongoDB database as well as export files. It does
not use a fallback database. Initialize the schema first, then run from the
workspace root:

```powershell
.\.venv\Scripts\python.exe -m backend.app.generator.cli --scale starter
```

The default starter mode writes under `generated-data/` (ignored by Git). For
the full challenge volumes:

```powershell
.\.venv\Scripts\python.exe -m backend.app.generator.cli --scale full
```

Both use seed `20261022`. CSV and JSON Lines files are produced per collection,
along with `manifest.json` containing row counts and SHA-256 checksums. The
checksums cover deterministic dataset rows and exclude `generation_runs`,
whose audit timestamps reflect wall-clock execution. Full scale writes
20,000 customers, 10,000 products, 500,000 sessions and 100,000 orders;
counts for derived collections are described in the
[generation rules](docs/data_generation.md).

Anomaly fixtures are opt-in and remain separate from baseline entity records:

```powershell
.\.venv\Scripts\python.exe -m backend.app.generator.cli --scale starter --inject-anomalies
```

Validate the latest completed generation run, or select one explicitly:

```powershell
.\.venv\Scripts\python.exe -m backend.app.validation.cli
.\.venv\Scripts\python.exe -m backend.app.validation.cli --generation-run-id RUN...
```

Validation writes issue-level CSV/JSONL and a summary under
`validation-output/`, and inserts issues into MongoDB. Its deterministic
fixtures cover purchase-before-view, missing category reference, test-to-train
leakage and discontinued/unavailable recommendations. See the
[validation and anomaly rules](docs/data_generation.md).

## Recommendation API

The recommendation endpoints use training-window inputs only. They persist
recommendation records, model runs and held-out evaluation results to MongoDB.
Set the supplied `MONGODB_URI`, initialize the schema and generate a dataset
before calling them.

- `POST /api/v1/recommendations/customers/{customer_id}` with
  `{"strategy":"hybrid","k":10,"as_of_time":"2025-10-01T00:00:00Z"}`
  generates recommendations. Strategy can be `popularity`, `content`, or
  `hybrid`; the default strategy is hybrid.
- `GET /api/v1/recommendations/customers/{customer_id}` retrieves stored
  recommendations.
- `POST /api/v1/recommendations/evaluations` with
  `{"k_values":[5,10]}` evaluates all strategies against test-split purchase
  labels only.
- `GET /api/v1/recommendations/evaluations` retrieves persisted metric results.
- `GET /api/v1/recommendations/strategies` describes model version, features,
  ranking weights and cold-start fallback.

Evaluation reports Precision@K, Recall@K, NDCG@K, Hit Rate@K, catalog coverage
and cold-start coverage with denominators and skipped-user counts. Metrics are
null with `insufficient_test_data` when no users have eligible held-out
relevance. Strategy formulas, availability-at-time rules and metric
denominators are documented in
[recommendations.md](docs/recommendations.md). Ground-truth labels remain
outside model-input repositories and the recommendation request API.

## Frontend

The React dashboard includes a system overview, deterministic data generation,
product catalog, recommendation explorer, validation issue browser and model
evaluation comparison. It reads business data through FastAPI; MongoDB
credentials are never placed in the frontend.

Copy `frontend\.env.example` to `frontend\.env.local` when the backend is not
using its local default URL, and set `VITE_API_BASE_URL` to the FastAPI origin.
The backend permits local Vite development origins on ports 5173 and 4173.

```powershell
Set-Location C:\CandidateWorkspace\frontend
npm install
npm run dev
```

The dashboard cannot show project records or run database-backed operations
until FastAPI has a caller-supplied, reachable `MONGODB_URI`. Generation is
append-only and rejects a database that already contains dataset records; it
does not clear collections. Full-scale generation can take substantial time,
and job state is held in the running API process. See the
[frontend integration notes](docs/frontend.md) for routes and limitations.

## Tests

From the workspace root:

```powershell
python -m pytest
```

Health, schema, repository-boundary, generator, recommendation, metric and API
tests run without requiring a MongoDB server. Frontend checks run from
`frontend\` using `npm run build` and `npm run lint`. Live database-backed
dashboard, generation, catalog, validation, recommendation and evaluation
features require the supplied MongoDB connection.
