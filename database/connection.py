"""
database/connection.py — SQLAlchemy engine and session factory.

Usage:
    from database.connection import init_db, get_session

    init_db()                    # Create all tables (idempotent)
    with get_session() as sess:  # Yields a session, commits on exit
        ...

Database URL handling:
    - sqlite:///<path>           → local file (default for dev/test)
    - sqlite:///:memory:         → in-memory (used by tests)
    - postgres://...             → normalized to postgresql+psycopg2://
    - postgresql://...           → normalized to postgresql+psycopg2://
    - postgresql+psycopg2://...  → used as-is

Neon (and other managed Postgres providers) typically issue connection strings
in the legacy ``postgres://`` form. SQLAlchemy 2.x rejects that scheme, so we
normalise eagerly and force the psycopg2 driver to match the pinned dependency
in requirements.txt.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config import DATABASE_URL
from database.models import Base

_engine: Optional[Engine] = None
_SessionFactory: Optional[sessionmaker] = None


def _normalize_db_url(url: str) -> str:
    """Normalise a database URL for SQLAlchemy 2.x.

    - ``postgres://...`` (Neon, Heroku-style) → ``postgresql://...``
    - ``postgresql://...`` (no driver) → ``postgresql+psycopg2://...``
    - All other schemes (sqlite, postgresql+psycopg2, etc.) returned unchanged.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


def get_engine() -> Engine:
    """Return (and lazily create) the shared SQLAlchemy engine."""
    global _engine
    if _engine is None:
        url = _normalize_db_url(DATABASE_URL)
        connect_args: dict = {}
        engine_kwargs: dict = {"echo": False}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        else:
            # Managed Postgres (Neon) closes idle connections aggressively;
            # pool_pre_ping detects stale connections before they cause errors.
            engine_kwargs["pool_pre_ping"] = True
        _engine = create_engine(
            url,
            connect_args=connect_args,
            **engine_kwargs,
        )
    return _engine


def _apply_schema_migrations(engine: Engine) -> None:
    """Add any columns present in ORM models but missing from existing DB tables.

    Idempotent: skips columns that already exist. Extend this list whenever a
    new column is added to an existing model without a full DB reset.

    Dialect-aware: column DDL is rewritten for Postgres (TIMESTAMPTZ, BOOLEAN,
    DOUBLE PRECISION) so the same migration list works on both SQLite and
    Postgres deployments.
    """
    inspector = inspect(engine)
    is_postgres = engine.dialect.name == "postgresql"

    # Logical type → dialect-specific DDL fragment.
    if is_postgres:
        types = {
            "JSON": "JSON",
            "FLOAT": "DOUBLE PRECISION",
            "BOOL": "BOOLEAN",
            "TIMESTAMP": "TIMESTAMP WITH TIME ZONE",
            "VARCHAR_24": "VARCHAR(24)",
            "VARCHAR_64": "VARCHAR(64)",
            "VARCHAR_128": "VARCHAR(128)",
        }
    else:  # sqlite (and any other forgiving dialect)
        types = {
            "JSON": "JSON",
            "FLOAT": "REAL",
            "BOOL": "INTEGER",
            "TIMESTAMP": "DATETIME",
            "VARCHAR_24": "VARCHAR(24)",
            "VARCHAR_64": "VARCHAR(64)",
            "VARCHAR_128": "VARCHAR(128)",
        }

    migrations = [
        # (table_name, column_name, column_definition)
        ("cognitive_profiles", "interaction_scores", f"{types['JSON']} DEFAULT NULL"),
        ("bias_metrics", "dei_ci_lower", f"{types['FLOAT']} DEFAULT NULL"),
        ("bias_metrics", "dei_ci_upper", f"{types['FLOAT']} DEFAULT NULL"),
        ("bias_metrics", "ocs_ci_lower", f"{types['FLOAT']} DEFAULT NULL"),
        ("bias_metrics", "ocs_ci_upper", f"{types['FLOAT']} DEFAULT NULL"),
        ("bias_metrics", "lai_ci_lower", f"{types['FLOAT']} DEFAULT NULL"),
        ("bias_metrics", "lai_ci_upper", f"{types['FLOAT']} DEFAULT NULL"),
        ("bias_metrics", "ci_low_confidence", f"{types['BOOL']} DEFAULT NULL"),
        # v6 auth fields
        ("users", "username", f"{types['VARCHAR_64']} DEFAULT NULL"),
        ("users", "password_hash", f"{types['VARCHAR_128']} DEFAULT NULL"),
        ("users", "last_login_at", f"{types['TIMESTAMP']} DEFAULT NULL"),
        # v6 survey discriminator
        ("user_surveys", "survey_type", f"{types['VARCHAR_24']} DEFAULT 'session_level'"),
    ]
    with engine.connect() as conn:
        for table, column, col_def in migrations:
            if not inspector.has_table(table):
                continue
            existing = {col["name"] for col in inspector.get_columns(table)}
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}"))
                conn.commit()


def init_db() -> None:
    """Create all tables defined in models.py (no-op if they already exist)."""
    engine = get_engine()
    # For existing dev DBs with new columns added to BiasMetric, re-run `python -m database.seed` to apply create_all.
    Base.metadata.create_all(bind=engine)
    _apply_schema_migrations(engine)


def _get_session_factory() -> sessionmaker:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), autoflush=True, autocommit=False)
    return _SessionFactory


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Context manager that provides a transactional database session.

    Commits on clean exit; rolls back on exception.
    """
    factory = _get_session_factory()
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
