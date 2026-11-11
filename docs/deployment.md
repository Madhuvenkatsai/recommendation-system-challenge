# Deployment readiness (not deployed)

No hosting platform or production deployment instructions have been supplied.
Do not deploy until these platform-specific settings and operations are
approved.

## Configuration

- Store `MONGODB_URI` in the host's secret manager; preserve
  `MONGODB_DATABASE=recommendation_challenge`. Never expose the URI in
  frontend variables, logs, build arguments or source control.
- Set backend `CORS_ALLOWED_ORIGINS` to exact HTTPS frontend origins. The API
  rejects wildcard origins. Local Vite defaults are for development only.
- Set frontend build-time `VITE_API_BASE_URL` to the public API origin. It is
  public configuration and must never contain a database credential.
- Leave `MONGODB_COLLECTION_PREFIX` unset for canonical data, or set it to
  `full_` to select the isolated full-scale collections.
- Keep `.env` untracked; production secrets belong in the host's secret store.

## Runtime and health checks

The backend entry point is:

```text
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

Adapt the port binding to the host's injected port variable. `GET /health` is
an API liveness check. `GET /api/v1/health` performs a MongoDB ping and should
be used as a readiness/dependency check. Install backend requirements from
`backend/requirements.txt`; install frontend dependencies with `npm ci` and
build with `npm run build`.

## MongoDB Atlas network and access

The deployed backend must have outbound TLS connectivity to Atlas using its
generated DNS/SRV hostname and MongoDB's configured network port (typically
27017). Add only the hosting provider's documented, stable egress IP/CIDR to
Atlas Network Access after an authorized operator verifies it. Do not use a
world-open allowlist. Keep database user privileges least-privileged and
rotate credentials through the secret manager when required.

## Remaining deployment blockers

- Hosting provider, region, build/runtime instructions and domain are
  unspecified.
- Production API URL, frontend origin, host secret store and stable egress
  addresses are not available for verification.
- Operation job status is process-local. Run one API worker for the current
  dashboard/generation workflows or implement shared durable job tracking
  before horizontal scaling.
- Live Atlas ping does not certify the production host's DNS, network,
  credentials, capacity or permissions.
