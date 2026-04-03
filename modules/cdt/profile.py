"""
modules/cdt/profile.py — CognitiveProfile CRUD helpers.

Functions:
    get_or_create_profile — Fetch or initialise a user's CDT profile.
    get_profile           — Fetch (or None) for read-only access.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from database.models import CognitiveProfile


def get_or_create_profile(db_session: Session, user_id: int) -> CognitiveProfile:
    """Return the CognitiveProfile for *user_id*, creating a default one if absent.

    Default state: all bias intensities 0.0, risk_preference 0.0,
    stability_index 0.0, session_count 0.

    Args:
        db_session: Active SQLAlchemy session.
        user_id:    ID of the user.

    Returns:
        CognitiveProfile ORM instance (already added to session but not committed).
    """
    profile = (
        db_session.query(CognitiveProfile)
        .filter_by(user_id=user_id)
        .first()
    )
    if profile is None:
        profile = CognitiveProfile(
            user_id=user_id,
            bias_intensity_vector={
                "overconfidence": 0.0,
                "disposition": 0.0,
                "loss_aversion": 0.0,
            },
            risk_preference=0.0,
            stability_index=0.0,
            session_count=0,
        )
        db_session.add(profile)
        db_session.flush()
    return profile


def get_profile(db_session: Session, user_id: int) -> CognitiveProfile | None:
    """Return the CognitiveProfile for *user_id*, or None if it does not exist.

    Args:
        db_session: Active SQLAlchemy session.
        user_id:    ID of the user.

    Returns:
        CognitiveProfile instance or None.
    """
    return (
        db_session.query(CognitiveProfile)
        .filter_by(user_id=user_id)
        .first()
    )
