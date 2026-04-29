"""scripts/generate_sample_uat_csv.py — produce a sample export_uat_summary
CSV using a fresh in-memory database so reviewers can preview the format.

Run with::

    python -m scripts.generate_sample_uat_csv

Writes ``reports/uat_summary_sample.csv``.
"""

from __future__ import annotations

import csv
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import (
    Base, BiasMetric, MarketSnapshot, SessionError, SessionSummary, StockCatalog,
    UATFeedback, User, UserAction,
)
from modules.analytics.bias_metrics import compute_and_save_metrics
from modules.utils.export import export_uat_summary

STOCKS = [
    ("BBCA.JK", "BBCA", "Bank Central Asia", "Finance", "low"),
    ("TLKM.JK", "TLKM", "Telkom Indonesia", "Telecom", "low_medium"),
    ("ANTM.JK", "ANTM", "Aneka Tambang", "Mining", "high"),
    ("GOTO.JK", "GOTO", "GoTo Gojek Tokopedia", "Technology", "high"),
    ("UNVR.JK", "UNVR", "Unilever Indonesia", "Consumer", "medium"),
    ("BBRI.JK", "BBRI", "Bank Rakyat Indonesia", "Finance", "medium"),
]
BASE_DATE = date(2024, 4, 2)
ROUNDS = 14


def _bootstrap():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sess = sessionmaker(bind=engine)()

    for sid, ticker, name, sector, vol in STOCKS:
        sess.add(StockCatalog(
            stock_id=sid, ticker=ticker, name=name,
            sector=sector, volatility_class=vol, bias_role="sample",
        ))
    sess.flush()

    for sid, *_ in STOCKS:
        for d in range(50):
            sess.add(MarketSnapshot(
                stock_id=sid, date=BASE_DATE + timedelta(days=d),
                open=1000.0, high=1010.0, low=990.0, close=1000.0,
                volume=1_000_000, ma_5=1000.0, ma_20=1000.0,
                rsi_14=50.0, volatility_20d=0.02, trend="neutral",
                daily_return=0.0,
            ))
    sess.flush()
    return sess


def _seed_user(sess, alias: str, sus_pattern: tuple[int, ...]) -> int:
    u = User(alias=alias, experience_level="beginner")
    sess.add(u)
    sess.flush()
    sid = str(uuid.uuid4())
    for r in range(1, ROUNDS + 1):
        for stock_id, *_ in STOCKS:
            snap = sess.query(MarketSnapshot).filter_by(
                stock_id=stock_id, date=BASE_DATE + timedelta(days=r - 1),
            ).first()
            sess.add(UserAction(
                user_id=u.id, session_id=sid, scenario_round=r,
                stock_id=stock_id, snapshot_id=snap.id,
                action_type="hold", quantity=0, action_value=0.0,
                response_time_ms=300,
            ))
    sess.flush()
    compute_and_save_metrics(sess, u.id, sid)
    sess.add(SessionSummary(
        user_id=u.id, session_id=sid,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        rounds_completed=ROUNDS, status="completed",
    ))
    sess.add(UATFeedback(
        user_id=u.id, session_id=sid,
        sus_q1=sus_pattern[0], sus_q2=sus_pattern[1],
        sus_q3=sus_pattern[2], sus_q4=sus_pattern[3],
        sus_q5=sus_pattern[4], sus_q6=sus_pattern[5],
        sus_q7=sus_pattern[6], sus_q8=sus_pattern[7],
        sus_q9=sus_pattern[8], sus_q10=sus_pattern[9],
        open_confusing="Tidak ada yang membingungkan." if alias == "penguji_01" else "Grafik radar sedikit ramai.",
        open_useful="Penjelasan bias terasa relevan." if alias == "penguji_01" else "Ekspor CSV sangat membantu.",
    ))
    if alias == "penguji_02":
        sess.add(SessionError(
            user_id=u.id, session_id=sid, error_type="ui_warning",
            message="Tooltip overflow on mobile (sample).",
        ))
    sess.flush()
    return u.id


def main() -> None:
    sess = _bootstrap()
    _seed_user(sess, "penguji_01", (5, 1, 4, 2, 5, 1, 5, 2, 4, 1))
    _seed_user(sess, "penguji_02", (4, 2, 4, 3, 4, 2, 3, 3, 4, 2))
    sess.flush()

    rows = export_uat_summary(sess)
    out = Path(__file__).resolve().parents[1] / "reports" / "uat_summary_sample.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {out}")


if __name__ == "__main__":
    main()
