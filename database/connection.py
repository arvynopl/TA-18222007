"""
database/connection.py — SQLAlchemy engine and session factory.

Usage:
    from database.connection import init_db, get_session

    init_db()                    # Create all tables (idempotent)
    with get_session() as sess:  # Yields a session, commits on exit
        ...
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


def get_engine() -> Engine:
    """Return (and lazily create) the shared SQLAlchemy engine."""
    global _engine
    if _engine is None:
        connect_args = {}
        if DATABASE_URL.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _engine = create_engine(
            DATABASE_URL,
            connect_args=connect_args,
            echo=False,
        )
    return _engine


def _apply_schema_migrations(engine: Engine) -> None:
    """Add any columns present in ORM models but missing from existing DB tables.

    Idempotent: skips columns that already exist. Extend this list whenever a
    new column is added to an existing model without a full DB reset.
    """
    inspector = inspect(engine)
    migrations = [
        # (table_name, column_name, column_definition)
        ("cognitive_profiles", "interaction_scores", "JSON DEFAULT NULL"),
    ]
    with engine.connect() as conn:
        for table, column, col_def in migrations:
            existing = {col["name"] for col in inspector.get_columns(table)}
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}"))
                conn.commit()


def init_db() -> None:
    """Create all tables defined in models.py (no-op if they already exist)."""
    engine = get_engine()
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
