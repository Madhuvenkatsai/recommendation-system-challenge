# End-to-end project walkthrough

This walkthrough describes the existing implementation and safe operation.
It does not deploy the application or regenerate an already populated
namespace.

## 1. Architecture

- `frontend/`: React + Vite dashboard; API calls use `VITE_API_BASE_URL`.
- `backend/`: FastAPI routes and separate generation, repository, validation,
  recommendation and evaluation modules.
- MongoDB Atlas: runtime source of truth; backend only, no browser credentials.
- `database/`: MongoDB schema, indexes, data dictionary and relationships.
- `generated-data/`: ignored reproducibility/export artifacts.

## 2. Configure and start MongoDB/API

Use the ignored root `.env` or process environment for
`MONGODB_URI` and `MONGODB_DATABASE`. Never copy credentials into tracked
files. The backend loads the workspace-root `.env` independently of the
terminal's current directory. For the existing challenge data, the expected
database is `recommendation_challenge`.

From `C:\CandidateWorkspace`, start FastAPI:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Check `GET /health` for API liveness and `GET /api/v1/health` for the
MongoDB ping. Initialize schema/indexes only when needed:

```powershell
.\.venv\Scripts\python.exe -m backend.app.db.initialize
```

## 3. Generate a starter dataset

On an empty canonical generated-data namespace:

```powershell
.\.venv\Scripts\python.exe -m backend.app.generator.cli --scale starter --inject-anomalies
```

The fixed seed is `20261022`. Generation streams parents before dependents,
preserves bounded write batches and appends lifecycle-event history. It refuses
to write into collections that already contain records. Do not rerun this
command against the already populated challenge database.

To preserve a clean baseline instead, omit `--inject-anomalies`; anomaly
fixtures are chosen at generation time and are not added later to a completed
run.

## 4. Validate and inspect anomalies

```powershell
.\.venv\Scripts\python.exe -m backend.app.validation.cli
```

Read `validation-output/validation_summary.json` and issue CSV/JSONL. Each
finding should identify the validation type, severity, generation run and
source record IDs. The four controlled anomalies reside in
`anomaly_fixtures`; they never mutate baseline entity records.

## 5. Generate recommendations and evaluate

Start the backend with the selected database and use the dashboard's
Recommendation Explorer, or call the API:

```powershell
Invoke-RestMethod -Method Get http://127.0.0.1:8000/api/v1/customers?limit=1
```

Use an actual returned customer ID in
`POST /api/v1/recommendations/customers/{customer_id}` with a strategy such as
`{"strategy":"hybrid","k":10}`. Then evaluate held-out test labels:

```powershell
Invoke-RestMethod -Method Post `
  -ContentType 'application/json' `
  -Body '{"k_values":[5,10]}' `
  http://127.0.0.1:8000/api/v1/recommendations/evaluations
```

Evaluation reports Precision@K, Recall@K, NDCG@K, Hit Rate@K, catalog
coverage and cold-start coverage. Test labels are accessed only by the
evaluation repository, never passed to recommendation model inputs.

## 6. Operate the dashboard

In another terminal:

```powershell
Set-Location C:\CandidateWorkspace\frontend
npm ci
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173/`. Navigate among Dashboard, Data Generation,
Product Catalog, Recommendation Explorer, Validation and Evaluation.
Dashboard metrics are API/MongoDB-backed. Unavailable data displays as an
error/unavailable state; an empty connected database reports real zero counts.

## 7. Export and reproduce

Starter exports are written under ignored `generated-data/`. Full-scale exports
use `generated-data-full/`. Each dataset includes CSV, JSON array, JSONL and
`seed_data.sql`; `manifest.json` contains counts and SHA-256 hashes. The SQL
file is a SQLite-compatible relational representation only; MongoDB remains
the application database. Existing export files are not overwritten. A
verified starter generator snapshot is available under
`exports/starter-submission/` (19 collections, 19,161 generated rows); it is
not a database dump, so persisted recommendation and evaluation results remain
in MongoDB.

Repeatability is verified by comparing generated row counts and canonical
checksums for the same configuration. Audit timestamps in `generation_runs`
are intentionally excluded from deterministic dataset hashes. Unit tests use
discard/in-memory targets rather than erasing database collections to repeat
generation.

## 8. Full-scale namespace and preflight

Full mode uses the same fixed seed and required target volumes, but writes to
`full_`-prefixed collections inside the same configured database. This avoids
the starter/full sequential-ID collision and prevents their events from
mixing in training/evaluation. The default API view remains on canonical
collections; set `MONGODB_COLLECTION_PREFIX=full_` to view/validate full data.
The CLI refuses to start if any prefixed target collection contains records.

Before full-scale execution, verify Atlas storage/throughput and local free
space for database indexes plus four export representations. A failed
multi-million-row run is not automatically rolled back; inspect the prefixed
collections and preserve partial records rather than deleting them.

## 9. Deployment boundary

Deployment is deliberately not performed. The hosting platform and deployment
instructions are not yet specified. See the [deployment readiness
notes](deployment.md) for environment, CORS, health-check, Atlas-network and
single-worker limitations.
