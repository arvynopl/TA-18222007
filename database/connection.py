"""
database/connection.py — SQLAlchemy engine and session factory.

Usage:
    from database.connection import init_db, get_session

    init_db()                    # Create all tables (idempotent)
    with get_session() as sess:  # Yields a session, commits on exit
        ...
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config import DATABASE_URL
from database.models import Base

_engine: Engine | None = None
_SessionFactory: sessionmaker | None = None


def get_engine() -> Engine:
    """Return (and lazily create) the shared SQLAlchemy engine."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False},  # needed for SQLite + threads
            echo=False,
        )
    return _engine


def init_db() -> None:
    """Create all tables defined in models.py (no-op if they already exist)."""
    Base.metadata.create_all(bind=get_engine())


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
