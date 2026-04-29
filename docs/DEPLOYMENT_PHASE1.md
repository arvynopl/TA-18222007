# Deployment — Phase 1: Database Externalisation (SQLite → Neon Postgres)

This document captures the database-layer changes required to make the CDT
prototype safe for Streamlit Community Cloud. Streamlit Cloud containers are
ephemeral: any data written to a local SQLite file is lost on every redeploy.
For UAT (≥100 testers), data must live on a managed Postgres such as Neon.

## TL;DR

1. Provision a free-tier Neon Postgres project (region: `ap-southeast-1` if
   available, else nearest to Indonesia).
2. Set `CDT_DATABASE_URL` to the Neon connection string in your local `.env`
   (for development) and as a Streamlit Cloud secret (for production).
3. Run `python -m database.seed` once against the Neon DB to populate
   `stock_catalog` (12 rows) and `market_snapshots` (~2 826 rows).
4. Run `pytest tests/test_postgres_compat.py -v` to confirm end-to-end writes.

The default behaviour (unset `CDT_DATABASE_URL`) is unchanged: the app falls
back to a local SQLite file, which keeps `pytest tests/` and existing dev
workflows intact.

## How to set `CDT_DATABASE_URL` for Neon

### Local development

Create a `.env` file at the repo root (already covered by `.gitignore`):

```bash
# .env — DO NOT COMMIT
CDT_DATABASE_URL='postgresql://<user>:<password>@<host>.neon.tech/<dbname>?sslmode=require'
```

Then either source it in your shell or use a loader (`python-dotenv`,
`direnv`). Example one-shot:

```bash
export $(grep -v '^#' .env | xargs)
streamlit run app.py
```

### Streamlit Community Cloud

In the app settings → **Secrets**, add a TOML block:

```toml
CDT_DATABASE_URL = "postgresql://<user>:<password>@<host>.neon.tech/<dbname>?sslmode=require"
```

Streamlit injects each top-level key as an environment variable, so
`config.py` picks it up via `os.environ.get("CDT_DATABASE_URL")`.

### URL forms accepted

`database/connection.py` normalises three forms to the same final URL:

| Input                                | Normalised to                                  |
| ------------------------------------ | ---------------------------------------------- |
| `postgres://...`                     | `postgresql+psycopg2://...`                    |
| `postgresql://...`                   | `postgresql+psycopg2://...`                    |
| `postgresql+psycopg2://...`          | unchanged                                      |

Neon issues `postgres://` URLs by default — no manual rewrite needed.

## How to run the Postgres compat test locally

```bash
# 1. Install the binary driver (pinned in requirements.txt)
pip install -r requirements.txt

# 2. Point at a Postgres DB (use a throwaway Neon branch or a local Docker pg)
export CDT_DATABASE_URL='postgresql://<user>:<password>@<host>.neon.tech/<dbname>?sslmode=require'

# 3. Run the compat tests (skipped automatically when the URL is unset / sqlite)
pytest tests/test_postgres_compat.py -v
```

Expected output: 4 tests passing (`init_db`, seed idempotency, log_action
roundtrip, JSON column roundtrip). Each test cleans up its own rows; the
schema itself is left in place for follow-up runs and for the seeded reference
data.

## What changed in this phase

### `database/connection.py`

- Added `_normalize_db_url()` — rewrites `postgres://` and bare
  `postgresql://` URLs to the explicit `postgresql+psycopg2://` form so
  SQLAlchemy 2.x and the pinned driver stay aligned.
- Added `pool_pre_ping=True` for non-SQLite engines. Neon recycles idle
  serverless connections; pre-ping detects stale ones and reconnects without
  surfacing a `psycopg2.OperationalError` to the user.
- Made `_apply_schema_migrations()` dialect-aware. The legacy `ALTER TABLE`
  fragments (`REAL`, `INTEGER`, `DATETIME`) are now expanded per-dialect:
    - On Postgres: `DOUBLE PRECISION`, `BOOLEAN`, `TIMESTAMP WITH TIME ZONE`.
    - On SQLite: unchanged (`REAL`, `INTEGER`, `DATETIME`).
  Fresh deployments hit `Base.metadata.create_all()` and skip these migrations
  entirely; the dialect awareness only matters for partially-upgraded
  databases.

### `requirements.txt`

- Added `psycopg2-binary>=2.9,<3`. The `-binary` distribution ships compiled
  wheels and avoids the `pg_config` / `libpq-dev` build dependency that
  Streamlit Cloud's build environment may lack.

### `tests/test_postgres_compat.py`

- New module. Auto-skips unless `CDT_DATABASE_URL` starts with `postgres` /
  `postgresql`. Verifies: schema creation, seed-style upsert, full
  `log_action()` roundtrip, JSON column persistence.

## Postgres-compatibility flags (no code change in this phase)

The following items work correctly on Postgres but are flagged for awareness.
None of them are blockers for Phase 1; they are documented here so they do
not surprise us during UAT.

### `DateTime` columns without `timezone=True`

The following ORM fields are declared as `DateTime` (tz-naive) even though
their default values are tz-aware (`datetime.now(timezone.utc)`):

- `User.created_at`
- `UserAction.timestamp`
- `BiasMetric.computed_at`
- `CognitiveProfile.last_updated_at`
- `FeedbackHistory.delivered_at`
- `ConsentLog.created_at`
- `UserSurvey.submitted_at`
- `SessionSummary.started_at`, `SessionSummary.completed_at`
- `CdtSnapshot.snapshotted_at`
- `PostSessionSurvey.submitted_at`

**Effect on Postgres:** the column is created as `TIMESTAMP WITHOUT TIME ZONE`.
The tz-aware Python value has its offset stripped on insert (the wall-clock
UTC component is preserved). Reads return tz-naive datetimes. All comparisons
remain consistent because every value originates from `timezone.utc`, but
analytics queries that join against external tz-aware timestamps must
explicitly tag the data as UTC.

**Effect on SQLite:** stored as ISO strings with offset; reads return tz-aware
datetimes. Behaviour differs slightly between dialects.

**Recommendation (deferred):** in a future cleanup phase, change these to
`DateTime(timezone=True)`. This would require a one-shot Alembic migration on
the live Neon DB. Out of scope for Phase 1.

### `JSON` (vs `JSONB`) on Postgres

`CognitiveProfile.bias_intensity_vector` and `CognitiveProfile.interaction_scores`
use SQLAlchemy's generic `JSON` type, which maps to `JSON` (text-backed) on
Postgres. For UAT-scale workloads (~100 users, single-digit GB), `JSON` is
adequate. If we later need indexed key-path queries, a switch to `JSONB`
(`from sqlalchemy.dialects.postgresql import JSONB`) and a column rewrite
would be needed.

### Seed idempotency

Both `seed_stock_catalog()` and `seed_market_snapshots()` check for existing
rows in Python before inserting, so a re-run is a no-op. Behaviour is
identical on Postgres and SQLite. The `UniqueConstraint` on
`(stock_id, date)` provides a database-level safety net if two processes
race the seed simultaneously — the second process will hit `IntegrityError`
and roll back its open transaction. For our single-user dev/UAT workflow this
race is not expected.

## Verification

```bash
# Default SQLite suite — must remain green.
pytest tests/ -v --tb=short

# Postgres compat suite — runs only when CDT_DATABASE_URL is set.
export CDT_DATABASE_URL='postgresql://...'
pytest tests/test_postgres_compat.py -v
```

Both runs are required before promoting Phase 1 to `main`.
