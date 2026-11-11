# MongoDB database layer

MongoDB is the only supported runtime database. The application uses PyMongo
and reads `MONGODB_URI` and `MONGODB_DATABASE` from process environment
variables or the workspace-root `.env` file. Explicit process environment
variables take precedence. `MONGODB_URI` is required;
`MONGODB_DATABASE` defaults to `product_recommendations`. Credentials and
connection strings are not included in the repository. Optional
`MONGODB_COLLECTION_PREFIX=full_` selects an isolated collection namespace in
the same database.

## Initialize collections and indexes

From `C:\CandidateWorkspace`, after configuring the ignored root `.env` or
setting `MONGODB_URI` in the current PowerShell environment:

```powershell
.\.venv\Scripts\python.exe -m backend.app.db.initialize
```

The initializer creates the 11 entity and eight supporting collections,
installs strict MongoDB JSON Schema validators, and ensures the declared
indexes. For existing collections, it compares the configured validator and
uses `collMod` only when a change is needed; named indexes are ensured
idempotently. It does not insert or generate application documents. Required
database privileges include listing collections, creating collections and
indexes, and changing validators when they differ.

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
  bounded MongoDB writes, CSV/JSON/JSONL/SQL exports and checksummed manifest. See the
  [generation rules](../docs/data_generation.md).

MongoDB cannot enforce foreign keys or multi-document lifecycle, chronology,
and arithmetic invariants. Those remain explicit application-level validation
responsibilities. The automated test suite uses fakes for schema behavior and
does not require or imply a live MongoDB connection; database commands require
a configured, reachable MongoDB instance.

## Isolated full-scale namespace

The full-scale generator writes to `full_`-prefixed collections in the same
configured database. It refuses to generate when any target collection already
contains data; it does not overwrite the starter collections or resolve ID
collisions by changing records. Set `MONGODB_COLLECTION_PREFIX=full_` when
starting the API or validation CLI to read that namespace. Leaving the setting
empty selects the existing canonical collections.

## SQL export representation

`seed_data.sql` is a SQLite-compatible relational export, not a MongoDB
initialization script. Top-level fields become columns; arrays and objects are
serialized as JSON text, UTC dates as ISO-8601 text, and Decimal128 values as
exact decimal text. Tables contain primary and applicable foreign keys with
deferred checks so generation-run references can be inserted in stream order.
The polymorphic lifecycle-event entity reference is enforced by application
validation rather than a SQL foreign key. MongoDB remains the runtime system
of record.
