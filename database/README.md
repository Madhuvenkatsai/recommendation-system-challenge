# MongoDB database layer

MongoDB is the only supported runtime database. The application uses the
already-installed PyMongo driver and requires a caller-supplied
`MONGODB_URI`; `MONGODB_DATABASE` defaults to `product_recommendations`.
Credentials and connection strings are not included in the repository.

## Initialize collections and indexes

From `C:\CandidateWorkspace`, after setting `MONGODB_URI` in the current
PowerShell environment:

```powershell
.\.venv\Scripts\python.exe -m backend.app.db.initialize
```

The initializer creates the 11 entity and seven supporting collections, installs
strict MongoDB JSON Schema validators, and ensures the declared indexes. It is
idempotent: existing collections receive updated validators via `collMod`,
and `create_index` ensures the same named indexes. It does not insert,
generate, or modify production documents. It requires a reachable MongoDB
instance and the database privileges needed to create collections, change
validators and create indexes.

## Documentation and implementation

- [Data dictionary](data_dictionary.md): fields, BSON types, required status,
  enums and field-level validation.
- [Relationships](relationships.md): entity cardinalities, reference rules and
  index inventory.
- `backend/app/db/schema.py`: canonical validator, collection and index
  definitions.
- `backend/app/db/initialize.py`: idempotent database initialization entry
  point.
- `backend/app/repositories/`: collection-bound access. Model-input repository
  bundles do not include ground-truth labels; evaluation has its own bundle.
- `backend/app/generator/`: fixed-seed generator, scale configuration,
  bounded MongoDB writes, CSV/JSONL exports and checksummed manifest. See the
  [generation rules](../docs/data_generation.md).

MongoDB cannot enforce foreign keys or multi-document lifecycle, chronology,
and arithmetic invariants. Those remain explicit application-level validation
responsibilities. The current workspace has no configured MongoDB URI or
server, so initialization and live collection validation have not been run
against MongoDB.
