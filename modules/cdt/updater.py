"""
modules/cdt/updater.py — EMA-based CognitiveProfile update logic.

After each simulation session the profile is updated using Exponential Moving
Averages (EMA) so that recent sessions carry more weight than older ones.

Functions:
    update_profile — Apply one EMA step and persist the updated profile.
"""

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy.orm import Session

import logging

from config import ALPHA, BETA, HIGH_VOLATILITY_CLASSES
from database.models import BiasMetric, CognitiveProfile, UserAction, StockCatalog
from modules.cdt.profile import get_or_create_profile
from modules.cdt.stability import compute_stability_index

logger = logging.getLogger(__name__)


def update_profile(
    db_session: Session,
    user_id: int,
    bias_metric: BiasMetric,
    session_id: str,
) -> CognitiveProfile:
    """Apply one EMA step to the user's CognitiveProfile using fresh bias metrics.

    EMA update rules (ALPHA = 0.3, BETA = 0.2):

        new_overconfidence = ALPHA × OCS  + (1 − ALPHA) × old_overconfidence
        new_disposition    = ALPHA × |DEI| + (1 − ALPHA) × old_disposition
        new_loss_aversion  = ALPHA × min(LAI/3, 1) + (1 − ALPHA) × old_loss_aversion

        observed_risk      = high_vol_trades / max(total_buy_sell_trades, 1)
        new_risk_pref      = BETA × observed_risk + (1 − BETA) × old_risk_pref

    Args:
        db_session:   Active SQLAlchemy session.
        user_id:      ID of the user to update.
        bias_metric:  BiasMetric computed for the just-completed session.
        session_id:   UUID string of the completed session (to query actions).

    Returns:
        The updated and flushed CognitiveProfile instance.
    """
    profile = get_or_create_profile(db_session, user_id)

    old = dict(profile.bias_intensity_vector)  # copy to avoid mutation issues

    # --- Bias intensity EMA update ---
    new_oc = ALPHA * (bias_metric.overconfidence_score or 0.0) + (1 - ALPHA) * old.get("overconfidence", 0.0)
    new_disp = ALPHA * abs(bias_metric.disposition_dei or 0.0) + (1 - ALPHA) * old.get("disposition", 0.0)
    new_la = (
        ALPHA * min((bias_metric.loss_aversion_index or 0.0) / 3.0, 1.0)
        + (1 - ALPHA) * old.get("loss_aversion", 0.0)
    )

    profile.bias_intensity_vector = {
        "overconfidence": new_oc,
        "disposition": new_disp,
        "loss_aversion": new_la,
    }
    logger.debug(
        "user=%s EMA update: OC %.3f→%.3f  DISP %.3f→%.3f  LA %.3f→%.3f",
        user_id,
        old.get("overconfidence", 0.0), new_oc,
        old.get("disposition", 0.0), new_disp,
        old.get("loss_aversion", 0.0), new_la,
    )

    # --- Risk preference EMA update ---
    # Observe the proportion of buy+sell actions on high-volatility stocks
    actions = (
        db_session.query(UserAction)
        .filter_by(user_id=user_id, session_id=session_id)
        .filter(UserAction.action_type.in_(["buy", "sell"]))
        .all()
    )

    high_vol_count = 0
    total_count = len(actions)
    # Batch-fetch all StockCatalog rows needed (Bug 10: eliminates N+1 queries)
    stock_ids_set = {a.stock_id for a in actions}
    stocks_map = {
        s.stock_id: s
        for s in db_session.query(StockCatalog)
        .filter(StockCatalog.stock_id.in_(stock_ids_set))
        .all()
    }
    for action in actions:
        stock = stocks_map.get(action.stock_id)
        if stock and stock.volatility_class in HIGH_VOLATILITY_CLASSES:
            high_vol_count += 1

    observed_risk = high_vol_count / max(total_count, 1)
    profile.risk_preference = BETA * observed_risk + (1 - BETA) * profile.risk_preference

    # --- Session count and stability ---
    profile.session_count += 1
    profile.stability_index = compute_stability_index(db_session, user_id)
    profile.last_updated_at = datetime.now(timezone.utc)

    db_session.flush()
    return profile
