"""
database/models.py — SQLAlchemy ORM entity definitions.

Seven entities:
    User, StockCatalog, MarketSnapshot, UserAction,
    BiasMetric, CognitiveProfile, FeedbackHistory
"""

from datetime import datetime, timezone, date as date_type
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, Float,
    ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


class User(Base):
    """Retail investor user identified by alias (no authentication)."""

    __tablename__ = "users"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    alias: str = Column(String(64), unique=True, nullable=False)
    experience_level: str = Column(
        String(20), nullable=False, default="beginner"
    )  # beginner | intermediate | advanced
    created_at: datetime = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    actions = relationship("UserAction", back_populates="user", lazy="dynamic")
    bias_metrics = relationship("BiasMetric", back_populates="user", lazy="dynamic")
    cognitive_profile = relationship(
        "CognitiveProfile", back_populates="user", uselist=False
    )
    feedback_history = relationship(
        "FeedbackHistory", back_populates="user", lazy="dynamic"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} alias={self.alias!r}>"


class StockCatalog(Base):
    """Metadata for the 6 IDX stocks used in the simulation."""

    __tablename__ = "stock_catalog"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    stock_id: str = Column(String(20), unique=True, nullable=False)  # e.g. "BBCA.JK"
    ticker: str = Column(String(10), nullable=False)                  # e.g. "BBCA"
    name: str = Column(String(128), nullable=False)
    sector: str = Column(String(64), nullable=False)
    volatility_class: str = Column(String(20), nullable=False)  # low|low_medium|medium|high
    bias_role: str = Column(Text, nullable=True)

    # Relationships
    snapshots = relationship("MarketSnapshot", back_populates="stock", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<StockCatalog {self.ticker} ({self.volatility_class})>"


class MarketSnapshot(Base):
    """One trading day of OHLCV + technical indicators for a stock."""

    __tablename__ = "market_snapshots"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    stock_id: str = Column(
        String(20), ForeignKey("stock_catalog.stock_id"), nullable=False
    )
    date: date_type = Column(Date, nullable=False)

    # OHLCV
    open: float = Column(Float, nullable=False)
    high: float = Column(Float, nullable=False)
    low: float = Column(Float, nullable=False)
    close: float = Column(Float, nullable=False)
    volume: int = Column(BigInteger, nullable=False)

    # Technical indicators (may be None for early rows)
    ma_5: Optional[float] = Column(Float, nullable=True)
    ma_20: Optional[float] = Column(Float, nullable=True)
    rsi_14: Optional[float] = Column(Float, nullable=True)
    volatility_20d: Optional[float] = Column(Float, nullable=True)
    trend: Optional[str] = Column(String(20), nullable=True)    # bullish|bearish|neutral
    daily_return: Optional[float] = Column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint("stock_id", "date", name="uq_snapshot_stock_date"),
    )

    # Relationships
    stock = relationship("StockCatalog", back_populates="snapshots")

    def __repr__(self) -> str:
        return f"<MarketSnapshot {self.stock_id} {self.date} close={self.close}>"


class UserAction(Base):
    """One decision (buy/sell/hold) made by a user during a simulation round."""

    __tablename__ = "user_actions"
    __table_args__ = (
        Index("ix_useraction_user_session", "user_id", "session_id"),
    )

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    user_id: int = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id: str = Column(String(36), nullable=False)    # UUID string
    scenario_round: int = Column(Integer, nullable=False)   # 1–14
    stock_id: str = Column(
        String(20), ForeignKey("stock_catalog.stock_id"), nullable=False
    )
    snapshot_id: int = Column(
        Integer, ForeignKey("market_snapshots.id"), nullable=False
    )
    action_type: str = Column(String(10), nullable=False)   # buy|sell|hold
    quantity: int = Column(Integer, nullable=False, default=0)
    action_value: float = Column(Float, nullable=False, default=0.0)
    response_time_ms: int = Column(Integer, nullable=False, default=0)
    timestamp: datetime = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="actions")
    snapshot = relationship("MarketSnapshot")
    stock = relationship("StockCatalog")

    def __repr__(self) -> str:
        return (
            f"<UserAction {self.action_type} {self.stock_id} "
            f"qty={self.quantity} round={self.scenario_round}>"
        )


class BiasMetric(Base):
    """Computed bias scores for a completed simulation session."""

    __tablename__ = "bias_metrics"
    __table_args__ = (
        Index("ix_biasmetric_user_session", "user_id", "session_id"),
    )

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    user_id: int = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id: str = Column(String(36), nullable=False)

    # Overconfidence
    overconfidence_score: Optional[float] = Column(Float, nullable=True)

    # Disposition Effect
    disposition_pgr: Optional[float] = Column(Float, nullable=True)
    disposition_plr: Optional[float] = Column(Float, nullable=True)
    disposition_dei: Optional[float] = Column(Float, nullable=True)

    # Loss Aversion
    loss_aversion_index: Optional[float] = Column(Float, nullable=True)

    computed_at: datetime = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="bias_metrics")

    def __repr__(self) -> str:
        ocs = f"{self.overconfidence_score:.3f}" if self.overconfidence_score is not None else "None"
        dei = f"{self.disposition_dei:.3f}" if self.disposition_dei is not None else "None"
        return f"<BiasMetric session={self.session_id[:8]} OCS={ocs} DEI={dei}>"


class CognitiveProfile(Base):
    """Longitudinal CDT profile updated via EMA after each session."""

    __tablename__ = "cognitive_profiles"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    user_id: int = Column(
        Integer, ForeignKey("users.id"), unique=True, nullable=False
    )

    # JSON: {"overconfidence": float, "disposition": float, "loss_aversion": float}
    bias_intensity_vector: dict = Column(JSON, nullable=False, default=lambda: {
        "overconfidence": 0.0,
        "disposition": 0.0,
        "loss_aversion": 0.0,
    })

    risk_preference: float = Column(Float, nullable=False, default=0.0)
    stability_index: float = Column(Float, nullable=False, default=0.0)
    session_count: int = Column(Integer, nullable=False, default=0)
    last_updated_at: datetime = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="cognitive_profile")

    def __repr__(self) -> str:
        return (
            f"<CognitiveProfile user={self.user_id} "
            f"sessions={self.session_count} stability={self.stability_index:.2f}>"
        )


class FeedbackHistory(Base):
    """Delivered feedback record for a specific bias in a session."""

    __tablename__ = "feedback_history"
    __table_args__ = (
        Index("ix_feedbackhistory_user_session", "user_id", "session_id"),
    )

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    user_id: int = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id: str = Column(String(36), nullable=False)
    bias_type: str = Column(String(30), nullable=False)    # overconfidence|disposition_effect|loss_aversion
    severity: str = Column(String(10), nullable=False)     # none|mild|moderate|severe
    explanation_text: str = Column(Text, nullable=True)
    recommendation_text: str = Column(Text, nullable=True)
    delivered_at: datetime = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="feedback_history")

    def __repr__(self) -> str:
        return (
            f"<FeedbackHistory {self.bias_type} severity={self.severity} "
            f"session={self.session_id[:8]}>"
        )
