"""
modules/logging_engine/validator.py — Session completeness validation.

Functions:
    validate_session_completeness — Verify all 14 × 6 action slots are filled.
"""

from sqlalchemy.orm import Session

from config import ROUNDS_PER_SESSION
from database.models import UserAction


def validate_session_completeness(
    session: Session, user_id: int, session_id: str
) -> dict:
    """Check whether a session has a UserAction for every round × stock combination.

    Args:
        session:    Active SQLAlchemy session.
        user_id:    User whose session to validate.
        session_id: UUID string of the session.

    Returns:
        Dict with keys:
            is_complete (bool),
            action_count (int),
            expected_count (int),
            missing_rounds (list[int])  — rounds with fewer than expected actions.
    """
    actions = (
        session.query(UserAction)
        .filter_by(user_id=user_id, session_id=session_id)
        .all()
    )

    # Count unique stocks that were ever acted on
    stock_ids_in_session = {a.stock_id for a in actions}
    expected_per_round = max(len(stock_ids_in_session), 1)
    expected_total = ROUNDS_PER_SESSION * expected_per_round

    # Group actions by round
    rounds_map: dict[int, list] = {}
    for action in actions:
        rounds_map.setdefault(action.scenario_round, []).append(action)

    missing_rounds = [
        r
        for r in range(1, ROUNDS_PER_SESSION + 1)
        if len(rounds_map.get(r, [])) < expected_per_round
    ]

    return {
        "is_complete": len(actions) >= expected_total and not missing_rounds,
        "action_count": len(actions),
        "expected_count": expected_total,
        "missing_rounds": missing_rounds,
    }
