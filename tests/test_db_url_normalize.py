"""tests/test_db_url_normalize.py — URL normalisation for the DB connection."""

from __future__ import annotations

import pytest

from database.connection import _normalize_db_url


def test_postgres_legacy_scheme_normalised_to_psycopg2():
    url = "postgres://u:p@ep-x.ap-southeast-1.aws.neon.tech/db?sslmode=require"
    out = _normalize_db_url(url)
    assert out.startswith("postgresql+psycopg2://")
    assert "ep-x.ap-southeast-1.aws.neon.tech" in out


def test_postgresql_scheme_gets_driver_appended():
    url = "postgresql://u:p@ep-x.us-east-2.aws.neon.tech/db?sslmode=require"
    out = _normalize_db_url(url)
    assert out.startswith("postgresql+psycopg2://")


def test_explicit_psycopg2_scheme_is_preserved():
    url = "postgresql+psycopg2://u:p@ep-x.eu-central-1.aws.neon.tech/db"
    assert _normalize_db_url(url) == url


def test_sqlite_scheme_is_unchanged():
    url = "sqlite:///:memory:"
    assert _normalize_db_url(url) == url


def test_surrounding_whitespace_is_stripped():
    url = "  postgresql://u:p@ep-x.us-east-1.aws.neon.tech/db  \n"
    out = _normalize_db_url(url)
    assert out.startswith("postgresql+psycopg2://")
    assert not out.endswith(("\n", " "))


def test_neon_url_missing_region_raises():
    """Bare ep-<id>.neon.tech (no region) cannot resolve; fail fast with hint."""
    url = "postgresql://u:p@ep-empty-night-amwbiyl1.neon.tech/db?sslmode=require"
    with pytest.raises(ValueError, match="missing the region segment"):
        _normalize_db_url(url)


def test_neon_url_with_region_passes_validation():
    url = (
        "postgresql://u:p@ep-empty-night-amwbiyl1.ap-southeast-1.aws.neon.tech"
        "/db?sslmode=require"
    )
    out = _normalize_db_url(url)
    assert "ap-southeast-1.aws.neon.tech" in out


def test_neon_pooler_host_with_region_passes_validation():
    url = (
        "postgresql://u:p@ep-empty-night-amwbiyl1-pooler.ap-southeast-1.aws.neon.tech"
        "/db?sslmode=require"
    )
    out = _normalize_db_url(url)
    assert "-pooler.ap-southeast-1.aws.neon.tech" in out


def test_non_neon_host_skips_validation():
    """Regular Postgres hosts (e.g. RDS) must not trip the Neon-specific check."""
    url = "postgresql://u:p@db.example.com/db"
    out = _normalize_db_url(url)
    assert "db.example.com" in out
