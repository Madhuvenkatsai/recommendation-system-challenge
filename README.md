# E-commerce Product Recommendation System

## 1. Project Title

**E-commerce Product Recommendation System**

## 2. Project Overview

This challenge project generates deterministic synthetic e-commerce data and
serves product recommendations through a React dashboard and FastAPI backend.
MongoDB is the runtime database and system of record. The implementation
separates model inputs from held-out ground-truth labels, supports chronological
evaluation, and records append-only cart and order lifecycle events.

The verified submission includes a starter-scale export snapshot. Full-scale
challenge targets and current starter counts are distinguished in the
dashboard; starter data does not represent completion of those targets.

## 3. Key Features

- Separate React + Vite frontend, FastAPI backend, and MongoDB database layers.
- MongoDB schema initialization with document validators and indexes.
- Seeded (`20261022`) starter/full synthetic data generation, bounded writes,
  isolated anomaly fixtures, and CSV, JSON, JSONL, and relational SQL exports.
- Chronological dataset splits, held-out ground-truth labels, data validation,
  and traceable anomaly findings.
- Append-only cart/order lifecycle history.
- Popularity, content-based, and hybrid recommendations with product
  eligibility and purchased-item exclusion rules.
- Persisted model/evaluation results and a dashboard for data, validation,
  recommendations, and evaluation.

## 4. Technology Stack

- **Frontend:** React, Vite, JavaScript
- **Backend:** Python 3.11+, FastAPI
- **Database:** MongoDB, accessed through PyMongo
- **Machine learning:** scikit-learn TF-IDF and cosine similarity
- **Testing:** pytest and frontend lint/build scripts

## 5. System Architecture

```text
React + Vite dashboard
        |
        | HTTP API (VITE_API_BASE_URL)
        v
FastAPI application
  |-- generation and export
  |-- MongoDB repositories
  |-- validation and anomaly reporting
  |-- recommendation and evaluation
        |
        v
MongoDB (runtime source of truth)
```

The frontend communicates with the backend and never receives MongoDB
credentials. MongoDB stores the 11 core entity collections and eight
supporting collections. Model-input repositories intentionally exclude
ground-truth labels, anomaly fixtures, validation issues, and lifecycle events;
evaluation and validation access those records through separate repository
surfaces.

See the [architecture documentation](docs/architecture.md) and
[collection relationship guide](database/relationships.md).

## 6. Project Directory Structure

```text
CandidateWorkspace/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI routes
│   │   ├── core/             # Environment and application configuration
│   │   ├── db/               # MongoDB schema and initialization
│   │   ├── generator/        # Deterministic generation and anomaly fixtures
│   │   ├── recommendations/  # Recommendation algorithms and metrics
│   │   ├── repositories/     # MongoDB data access boundaries
│   │   └── validation/       # Dataset validation and CLI
│   ├── requirements.txt
│   └── requirements-dev.txt
├── database/                 # Data dictionary and relationships
├── docs/                     # Architecture, operation, and feature guides
├── exports/starter-submission/ # Verified starter export snapshot
├── frontend/
│   ├── src/                  # React pages, components, and assets
│   └── package.json
├── tests/                    # Backend pytest suite
├── generated-data/           # Local generated exports (Git-ignored)
├── validation-output/        # Local validation reports (Git-ignored)
├── .env.example              # Placeholder-only backend environment template
└── README.md
```

## 7. Prerequisites

- Python 3.11 or newer.
- Node.js 20.19+ or 22.12+.
- A MongoDB instance and a caller-provided connection string for
  database-backed features.
- PowerShell for the commands below.

The API liveness route can start without MongoDB configured. The MongoDB health
route then reports `not_configured`; database-backed features require a
reachable MongoDB instance. MongoDB is never silently replaced with another
database.

## 8. Quick Start

1. From the project root, create a local `.env` from the placeholder template.
2. Edit `.env` locally and provide your MongoDB connection configuration.
   Never paste credentials into tracked files or share `.env`.
3. Start FastAPI in the first terminal.
4. Start the React development server in a second terminal.
5. Open [http://127.0.0.1:5173/](http://127.0.0.1:5173/).

Create the local environment file only if one does not already exist. If you
already have `.env`, keep it and update it locally rather than overwriting it:

```powershell
Set-Location C:\CandidateWorkspace
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Replace the placeholder values in the local `.env` with values supplied for
your MongoDB instance. If this is a fresh clone, install backend dependencies
once before starting the API:

```powershell
Set-Location C:\CandidateWorkspace
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
```

Then, in the first terminal:

```powershell
Set-Location C:\CandidateWorkspace
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

In the second terminal:

```powershell
Set-Location C:\CandidateWorkspace\frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

MongoDB must be configured and reachable for the dashboard to show stored
project data and for other database-backed operations. See
[Environment Configuration](#9-environment-configuration) and
[Backend Setup](#10-backend-setup).

## 9. Environment Configuration

The root `.env.example` contains placeholders only. Copy it to the ignored root
`.env` and set values locally; the README and frontend do not contain MongoDB
credentials. `.env` and environment-specific `.env.*` files are excluded from
Git, while `.env.example` is permitted.

| Variable | Purpose |
|---|---|
| `MONGODB_URI` | Required MongoDB connection URI for database-backed operations. |
| `MONGODB_DATABASE` | Database name; defaults to `recommendation_challenge`. |
| `MONGODB_COLLECTION_PREFIX` | Optional collection namespace, such as `full_`, in the same database. |
| `CORS_ALLOWED_ORIGINS` | Optional comma-separated list of exact frontend HTTP(S) origins. |
| `VITE_API_BASE_URL` | Optional FastAPI origin used by the frontend; defaults to `http://127.0.0.1:8000`. |

The backend loads the workspace-root `.env` independently of the current
working directory. Process environment values take precedence. By default,
CORS permits local Vite development/preview origins on ports 5173 and 4173;
production origins must be explicitly configured. The frontend's
`frontend/.env.example` is also a placeholder template.

## 10. Backend Setup

From the workspace root, create a virtual environment and install development
dependencies:

```powershell
Set-Location C:\CandidateWorkspace
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
```

Start the API from the workspace root:

```powershell
Set-Location C:\CandidateWorkspace
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

- `GET http://127.0.0.1:8000/health` checks API liveness.
- `GET http://127.0.0.1:8000/api/v1/health` pings MongoDB and returns HTTP 503
  with an explicit reason when MongoDB is not configured or unavailable.

## 11. MongoDB Schema Initialization

After MongoDB is available and the root `.env` or process environment contains
the connection settings, initialize collections, validators, and indexes from
the workspace root:

```powershell
Set-Location C:\CandidateWorkspace
.\.venv\Scripts\python.exe -m backend.app.db.initialize
```

Initialization is idempotent and does not insert or generate application
documents. It creates missing collections and indexes and updates a validator
when the configured definition differs. See the [database setup guide](database/README.md),
[data dictionary](database/data_dictionary.md), and
[collection relationships](database/relationships.md).

## 12. Synthetic Data Generation

Generation requires a configured, reachable MongoDB instance. It writes
deterministic records in bounded batches to MongoDB and writes CSV, JSON,
JSONL, SQL, and manifest exports to the output directory. It does not use a
fallback database. The fixed seed is `20261022`.

Run starter generation from the workspace root:

```powershell
Set-Location C:\CandidateWorkspace
.\.venv\Scripts\python.exe -m backend.app.generator.cli --scale starter
```

Starter exports default to `generated-data/`, which is ignored by Git. The
generator refuses to write when the selected collections already contain
dataset records; it does not clear or overwrite records. Do not run generation
against an already populated namespace.

The CLI also supports a separate full-scale namespace and output directory:

```powershell
Set-Location C:\CandidateWorkspace
.\.venv\Scripts\python.exe -m backend.app.generator.cli --scale full
```

Full mode uses `full_`-prefixed collections in the configured MongoDB database
and defaults to `generated-data-full/`. It refuses to generate if its target
collections contain records. Full-scale targets are 20,000 customers, 10,000
products, 500,000 sessions, and 100,000 orders; volumes for derived
collections are described in the [generation guide](docs/data_generation.md).
Full-scale generation has **not** been run for this submission.

Anomaly fixtures are opt-in and stored separately from clean baseline records.
Generate a starter dataset with the default set of controlled anomalies using:

```powershell
Set-Location C:\CandidateWorkspace
.\.venv\Scripts\python.exe -m backend.app.generator.cli --scale starter --inject-anomalies
```

This command also creates a dataset and therefore requires an empty target
namespace. The generator CLI additionally defines `--output-dir`, `--batch-size`,
and `--anomaly-types`; see `--help` for the supported values and use only with
an appropriate empty namespace.

Both scales use seed `20261022`. The export manifest records file names, row
counts, and SHA-256 checksums. Existing export files are not overwritten.
Deterministic row hashes exclude `generation_runs`, whose timestamps vary by
execution. The SQL export is SQLite-compatible relational output only; MongoDB
remains the runtime system of record.

## 13. Data Validation and Anomalies

Validate the latest completed generation run:

```powershell
Set-Location C:\CandidateWorkspace
.\.venv\Scripts\python.exe -m backend.app.validation.cli
```

The validator also accepts `--generation-run-id` to select a specific
completed run, `--output-dir` to choose the report directory, and `--batch-size`
to set the processing batch size. These options are defined by the
[validation CLI](backend/app/validation/cli.py). Validation writes issue-level
CSV/JSONL and a summary under `validation-output/`, and persists issues in
MongoDB.

The four controlled anomaly types are:

1. Purchase before a valid same-session product view.
2. Product references a missing category.
3. Test-period event assigned to training.
4. Recommendation includes a discontinued or unavailable product.

Fixtures retain expected labels and source IDs separately from clean records.
The validator checks references, chronology, arithmetic, lifecycle transitions,
split isolation, recommendation eligibility, and anomaly traceability. See
[data generation rules](docs/data_generation.md) and
[validation and anomaly handling](docs/validation.md).

## 14. Recommendation Engine

Recommendation requests use training-window inputs only. The training window
is chronological and half-open (`[start_at, end_at)`). Validation/test events,
ground-truth labels, anomaly fixtures, and lifecycle history are not model
features. Eligibility is evaluated at the requested `as_of_time`; unavailable
and discontinued products are excluded as documented, and prior completed
purchases are excluded. Cancelled and refunded orders do not count as purchases
for this exclusion.

Supported strategies are `popularity`, `content`, and `hybrid`; the default is
hybrid. Popularity uses training-window interaction weights (view = 1, cart
addition = 3, completed purchase = 5). Content uses scikit-learn TF-IDF over
product metadata and cosine similarity. Hybrid combines normalized popularity
and content scores with default weights of 0.5 each. Customers with no training
interactions use the training-window popularity fallback.

Recommendation API endpoints:

- `POST /api/v1/recommendations/customers/{customer_id}` generates a
  recommendation. Example request body:
  `{"strategy":"hybrid","k":10,"as_of_time":"2025-10-01T00:00:00Z"}`.
- `GET /api/v1/recommendations/customers/{customer_id}` retrieves stored
  recommendations.
- `POST /api/v1/recommendations/evaluations` evaluates strategies against
  held-out test labels. Example request body: `{"k_values":[5,10]}`.
- `GET /api/v1/recommendations/evaluations` retrieves persisted metric results.
- `GET /api/v1/recommendations/strategies` describes model versions, features,
  ranking weights, and cold-start behavior.

The request API does not expose ground-truth labels. See the
[recommendation and evaluation guide](docs/recommendations.md).

## 15. Evaluation Metrics

Evaluation compares eligible recommendations with held-out purchase labels
from the test split. It reports:

- **Precision@K** and **Recall@K**
- **NDCG@K** and **Hit Rate@K**
- **Catalog coverage** and **cold-start coverage**

Results include metric denominators, eligible/skipped user counts, label and
recommendation counts, and evaluation status. When there is no eligible held-out
relevance, metrics are `null` with `insufficient_test_data`; they are not
reported as successful zero scores. See the
[metric definitions and denominators](docs/recommendations.md#test-period-evaluation).

## 16. Frontend Setup

From the frontend directory, install the locked dependencies and start Vite:

```powershell
Set-Location C:\CandidateWorkspace\frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

Open [http://127.0.0.1:5173/](http://127.0.0.1:5173/). The dashboard includes
Dashboard, Data Generation, Product Catalog, Recommendation Explorer,
Validation, and Evaluation views. It displays live counts for all 11 core
entities and eight supporting collections. Actual counts, full-scale targets,
and progress are shown separately.

The frontend API client defaults to `http://127.0.0.1:8000`. If the backend
uses another origin, copy `frontend/.env.example` to `frontend/.env.local` and
set `VITE_API_BASE_URL` to the FastAPI origin. For production, configure the
frontend build-time API origin and the exact frontend origin in
`CORS_ALLOWED_ORIGINS`. MongoDB credentials must never be placed in frontend
configuration. See the [frontend integration guide](docs/frontend.md).

## 17. Testing

Run the backend test suite from the workspace root:

```powershell
Set-Location C:\CandidateWorkspace
.\.venv\Scripts\python.exe -m pytest
```

Check Python syntax and installed dependency consistency:

```powershell
Set-Location C:\CandidateWorkspace
.\.venv\Scripts\python.exe -m compileall backend\app tests
```

```powershell
Set-Location C:\CandidateWorkspace
.\.venv\Scripts\python.exe -m pip check
```

Run frontend lint and production build from `frontend/`:

```powershell
Set-Location C:\CandidateWorkspace\frontend
npm run lint
```

```powershell
Set-Location C:\CandidateWorkspace\frontend
npm run build
```

Backend tests cover health, schema, repository boundaries, generation,
recommendations, metrics, and APIs without requiring a live MongoDB server.
MongoDB-backed dashboard, generation, catalog, validation, recommendation, and
evaluation operations require a configured, reachable database.

## 18. Exports and Data Dictionary

The verified starter snapshot is in
[exports/starter-submission/](exports/starter-submission/), with a
[manifest](exports/starter-submission/manifest.json) containing file names,
row counts, and checksums. It is a reproducible generator snapshot, not a
MongoDB dump; persisted recommendation and evaluation results remain in
MongoDB. Generated files default to `generated-data/` (starter) and
`generated-data-full/` (full), both ignored by Git.

Exports include CSV, standard JSON arrays, JSON Lines, and `seed_data.sql`.
SQL is a SQLite-compatible relational representation with table definitions
and key constraints; it is not a MongoDB initialization script. Dates and
nested values are serialized for the relational export. MongoDB remains the
runtime database.

The [data dictionary](database/data_dictionary.md) documents fields, BSON
types, identifiers, and validation rules. The
[relationships guide](database/relationships.md) describes cardinalities,
references, and indexes.

## 19. Known Limitations

- The verified submission contains **starter-scale** data. Existing MongoDB
  starter counts do not represent full-scale completion.
- Full-scale targets are **20,000 customers, 10,000 products, 500,000 sessions,
  and 100,000 orders**.
- Full-scale generation was **not executed** for this submission because of
  resource limitations.
- Supported recommendation strategies are **popularity, content, and hybrid**.
  Collaborative filtering is **not implemented**.
- The local development URL is not a public deployment URL. The application
  has not been deployed.
- Generation and validation job status is process-local in the API; it does
  not survive an API restart.
- Generation refuses to write into populated target collections. A failed
  multi-collection generation can leave partial records, which are not
  automatically deleted or rolled back.
- MongoDB document validators do not enforce relational foreign keys or
  cross-document chronology; those constraints are checked by application
  validation.

See the [deployment readiness notes](docs/deployment.md) before planning a
deployment.

## 20. End-to-End Walkthrough

For the detailed operating sequence—including configuration, schema setup,
generation, MongoDB storage, validation, anomaly inspection, recommendation
generation, evaluation, dashboard use, exports, and reproducibility—see the
[end-to-end project walkthrough](docs/walkthrough.md).
