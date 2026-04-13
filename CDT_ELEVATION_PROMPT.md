# CDT Elevation — Claude Code Implementation Prompt
# TA-18222007 | Arvyno Pranata Limahardja | ITB STI
#
# Scope: Two targeted enhancements to elevate the CDT from a bias tracker
#        to a coupled, trajectory-aware cognitive model.
#
# TASK LIST:
#   TASK 1 — Activate Cross-Bias Interaction Synthesis (V2)
#   TASK 2 — Upgrade Trajectory Modifier to 3-Session Trend (V3)
#   TASK 3 — Write tests for both changes
#   TASK 4 — Run full test suite, verify 0 failures
#
# NOTE: PostSessionSurvey (V1) is ALREADY fully implemented.
#       DB model (PostSessionSurvey), UI (_render_post_session_survey),
#       and the call in render_feedback_page() are all in place.
#       Do NOT re-implement it.
#
# EXECUTION MODEL: Single Claude Code session. Execute tasks in order.
# After each task, run: pytest tests/ -v --tb=short

---

You are implementing two targeted enhancements to the CDT Bias Detection System
(TA-18222007). This is an ITB thesis project — a Streamlit-based Cognitive
Digital Twin for detecting behavioral biases in retail investors.

Read CLAUDE.md before starting. Adhere to all conventions there.

---

## HARD CONSTRAINTS (from CLAUDE.md — never violate)

- All user-facing text in Bahasa Indonesia
- datetime.now(timezone.utc) only — never datetime.utcnow()
- DB sessions via `with get_session() as sess:` — never hold across reruns
- Never import Streamlit in test files
- Never change DEI, OCS, LAI formulas
- Never restructure folders or rename modules

---

## CONTEXT: WHAT ALREADY EXISTS

Before writing any code, understand the current state:

**modules/cdt/interaction.py** — `compute_interaction_scores(db, user_id)`:
- Computes pairwise Pearson r: ocs_dei, ocs_lai, dei_lai
- Returns a dict like `{"ocs_dei": 0.82, "ocs_lai": 0.41, "dei_lai": None}`
- Returns None if fewer than 3 sessions exist
- Already called by `modules/cdt/updater.py:update_profile()` — result stored
  in `CognitiveProfile.interaction_scores` (JSON column)

**modules/feedback/generator.py** — `_get_cdt_modifier(...)`:
- Currently compares current_severity vs. prev_session (single-lag only)
- Has a stability_index warning for persistent patterns
- Called once per bias type inside `generate_feedback()`

**database/models.py** — `CognitiveProfile`:
- Has `interaction_scores: Optional[dict]` — already populated after session 3+
- Has `stability_index: float`, `session_count: int`
- `profile.interaction_scores` is accessible wherever `profile` is passed

**modules/feedback/renderer.py** — `render_feedback_page(...)`:
- Renders 3 bias cards, then `render_longitudinal_section()`, then CTAs,
  then `_render_post_session_survey()` (already done — do not touch)
- This is where the interaction synthesis section will be injected

---

## TASK 1 — Cross-Bias Interaction Synthesis

**Goal:** When a user has ≥ 5 sessions AND at least one pairwise Pearson r
exceeds ±0.65, display a "Pola Bias Gabungan" (Coupled Bias Pattern) card
on the feedback page. This elevates the CDT from three independent trackers
to a coupled cognitive model — the theoretical core of a Digital Twin.

**Threshold rationale:** r > 0.65 signals a strong behavioral coupling
(moderate-strong per Cohen 1988 convention). r < -0.65 signals a compensatory
pattern. Gate on session_count ≥ 5 so Pearson has enough data points.

### 1A — Add `_get_interaction_modifier()` to generator.py

**File:** `modules/feedback/generator.py`

Add this function after `_get_cdt_modifier()` (before `generate_feedback()`):

```python
_INTERACTION_THRESHOLD = 0.65  # Strong coupling threshold (Cohen 1988)
_MIN_SESSIONS_FOR_INTERACTION = 5


def _get_interaction_modifier(profile: CognitiveProfile) -> list[str]:
    """Return Bahasa Indonesia insight strings for strong cross-bias couplings.

    Reads interaction_scores from the CognitiveProfile (already computed and
    stored by update_profile() via compute_interaction_scores()).

    Returns an empty list when:
      - session_count < _MIN_SESSIONS_FOR_INTERACTION (insufficient data)
      - interaction_scores is None or empty
      - No pairwise r exceeds ±_INTERACTION_THRESHOLD

    Returns:
        List of insight strings (Bahasa Indonesia). Typically 0–2 items.
    """
    if profile.session_count < _MIN_SESSIONS_FOR_INTERACTION:
        return []

    scores = profile.interaction_scores
    if not scores:
        return []

    insights: list[str] = []

    ocs_dei = scores.get("ocs_dei")
    ocs_lai = scores.get("ocs_lai")
    dei_lai = scores.get("dei_lai")

    # OCS ↔ DEI: Overtrading often co-occurs with premature winner liquidation
    if ocs_dei is not None and abs(ocs_dei) >= _INTERACTION_THRESHOLD:
        if ocs_dei > 0:
            insights.append(
                "Sistem mendeteksi pola gabungan antara overconfidence dan efek "
                "disposisi: frekuensi trading yang tinggi cenderung muncul bersamaan "
                "dengan kecenderungan menjual keuntungan terlalu cepat. "
                "Pertimbangkan untuk mengurangi intensitas transaksi dan memberikan "
                "lebih banyak waktu bagi posisi menguntungkan untuk berkembang."
            )
        else:
            insights.append(
                "Pola kompensasi terdeteksi: ketika frekuensi trading meningkat, "
                "kamu justru cenderung menahan posisi menguntungkan lebih lama — "
                "ini mengindikasikan kehati-hatian yang lebih besar saat aktif trading."
            )

    # OCS ↔ LAI: High trading activity co-occurs with reluctance to cut losses
    if ocs_lai is not None and abs(ocs_lai) >= _INTERACTION_THRESHOLD:
        if ocs_lai > 0:
            insights.append(
                "Pola menarik terdeteksi: semakin sering kamu bertransaksi, semakin "
                "lama kamu menahan posisi yang merugi. Ini mengindikasikan bahwa "
                "aktivitas trading yang tinggi mungkin dipengaruhi oleh keengganan "
                "untuk merealisasi kerugian — kombinasi yang dapat menggerus modal "
                "secara signifikan."
            )
        else:
            insights.append(
                "Pola kompensasi terdeteksi: sesi dengan aktivitas trading tinggi "
                "justru disertai pengelolaan kerugian yang lebih disiplin. "
                "Ini adalah tanda kesadaran diri yang berkembang."
            )

    # DEI ↔ LAI: Both biases reinforce each other — selling winners too fast
    # AND holding losers too long amplifies portfolio damage
    if dei_lai is not None and abs(dei_lai) >= _INTERACTION_THRESHOLD:
        if dei_lai > 0:
            insights.append(
                "Dua pola bias yang saling memperkuat terdeteksi secara konsisten: "
                "kamu cenderung menjual keuntungan terlalu cepat sekaligus menahan "
                "kerugian terlalu lama. Kombinasi ini secara bersamaan memperbesar "
                "kerugian dan memperkecil keuntungan — dampaknya terhadap portofolio "
                "lebih besar dari kedua bias secara terpisah."
            )
        else:
            insights.append(
                "Pola kompensasi terdeteksi antara efek disposisi dan loss aversion: "
                "keduanya tidak selalu muncul bersamaan dalam perilaku tradingmu, "
                "menandakan pengendalian diri yang mulai berkembang pada salah satu dimensi."
            )

    return insights
```

Add the import for `_INTERACTION_THRESHOLD` and `_MIN_SESSIONS_FOR_INTERACTION`
as module-level constants (put them near the top of the file, after the existing
`_SEVERITY_RANK` dict).

### 1B — Add `render_interaction_synthesis()` to renderer.py

**File:** `modules/feedback/renderer.py`

Add this function after `render_longitudinal_section()` (before
`render_feedback_page()`):

```python
def render_interaction_synthesis(user_id: int, session_id: str) -> None:
    """Render a coupled-bias synthesis card when strong interactions are detected.

    Reads CognitiveProfile.interaction_scores (already stored) and calls
    _get_interaction_modifier() from the generator. Only renders when at least
    one pairwise Pearson r exceeds the threshold AND session_count >= 5.

    Args:
        user_id:    ID of the user.
        session_id: UUID of the current session (unused directly; passed for
                    future extensibility).
    """
    from database.models import CognitiveProfile
    from modules.feedback.generator import _get_interaction_modifier

    with get_session() as sess:
        profile = sess.query(CognitiveProfile).filter_by(user_id=user_id).first()
        if profile is None:
            return
        # Snapshot relevant fields before session closes
        session_count = profile.session_count
        interaction_scores = profile.interaction_scores
        stability_index = profile.stability_index

    # Build a temporary profile-like namespace for the modifier function
    # (avoids DetachedInstanceError — all data already extracted above)
    class _ProfileSnapshot:
        pass

    snap = _ProfileSnapshot()
    snap.session_count = session_count
    snap.interaction_scores = interaction_scores
    snap.stability_index = stability_index

    insights = _get_interaction_modifier(snap)  # type: ignore[arg-type]
    if not insights:
        return

    st.markdown("---")
    st.subheader("🔗 Pola Bias Gabungan")
    st.caption(
        "Analisis keterkaitan antar-bias berdasarkan riwayat multi-sesi kamu. "
        "Pola ini terdeteksi hanya setelah minimal 5 sesi selesai."
    )

    for insight in insights:
        st.info(insight)
```

### 1C — Inject the call into render_feedback_page()

**File:** `modules/feedback/renderer.py`

Inside `render_feedback_page()`, add the call to `render_interaction_synthesis()`
**after** the call to `render_longitudinal_section(user_id)` and **before**
the `st.divider()` that precedes the navigation CTAs.

Find this block (it appears after `render_longitudinal_section`):

```python
    render_longitudinal_section(user_id)

    # --- Session navigation CTAs ---
    st.divider()
```

Replace it with:

```python
    render_longitudinal_section(user_id)

    render_interaction_synthesis(user_id=user_id, session_id=session_id)

    # --- Session navigation CTAs ---
    st.divider()
```

---

## TASK 2 — Upgrade Trajectory Modifier to 3-Session Trend

**Goal:** Replace the single-lag severity comparison in `_get_cdt_modifier()`
with a 3-point trend classifier that uses raw `BiasMetric` values. This
provides a statistically richer trajectory signal and directly supports the
"mitigation evidence" narrative in the thesis (Bab VI).

**Current behavior:** Compares current severity label vs. the most recent
FeedbackHistory severity label — a single-step diff.

**New behavior:** Fetch the last 3 BiasMetric records (excluding the current
session), extract the normalized metric value, classify as "improving" /
"worsening" / "stable" / "volatile", and generate a 3-session trend statement.

### 2A — Add `_classify_bias_trajectory()` to generator.py

**File:** `modules/feedback/generator.py`

Add this helper function before `_get_cdt_modifier()`:

```python
_BIAS_METRIC_KEY: dict[str, str] = {
    "overconfidence": "overconfidence_score",
    "disposition_effect": "disposition_dei",
    "loss_aversion": "loss_aversion_index",
}


def _classify_bias_trajectory(
    db_session: Session,
    user_id: int,
    current_session_id: str,
    bias_type: str,
) -> str:
    """Classify the 3-session trend for a specific bias type.

    Fetches the last 3 BiasMetric records (excluding the current session),
    normalises the relevant metric to [0, 1], and returns a trajectory label.

    Normalisation (mirrors stability index logic):
      - overconfidence_score: already in [0, 1) — unchanged.
      - disposition_dei: abs(DEI) — captures magnitude regardless of sign.
      - loss_aversion_index: min(LAI / LAI_EMA_CEILING, 1.0).

    Returns:
        "improving"   — strictly decreasing over the 3 sessions (oldest→newest)
        "worsening"   — strictly increasing over the 3 sessions
        "volatile"    — non-monotonic (oscillating) pattern
        "stable"      — all three values within 0.05 of each other
        "insufficient"— fewer than 3 prior sessions available
    """
    from config import LAI_EMA_CEILING

    col_name = _BIAS_METRIC_KEY.get(bias_type)
    if col_name is None:
        return "insufficient"

    prior_metrics = (
        db_session.query(BiasMetric)
        .filter(
            BiasMetric.user_id == user_id,
            BiasMetric.session_id != current_session_id,
        )
        .order_by(BiasMetric.computed_at.asc())
        .all()
    )

    if len(prior_metrics) < 3:
        return "insufficient"

    # Take last 3 prior sessions (oldest → newest for trend direction)
    last_three = prior_metrics[-3:]

    def _normalize(metric: BiasMetric) -> float:
        if bias_type == "overconfidence":
            return metric.overconfidence_score or 0.0
        elif bias_type == "disposition_effect":
            return abs(metric.disposition_dei or 0.0)
        else:  # loss_aversion
            return min((metric.loss_aversion_index or 0.0) / LAI_EMA_CEILING, 1.0)

    vals = [_normalize(m) for m in last_three]
    a, b, c = vals[0], vals[1], vals[2]

    # Stability band: all values within 0.05 of each other → stable
    if max(vals) - min(vals) < 0.05:
        return "stable"

    if c < b < a:
        return "improving"
    if c > b > a:
        return "worsening"
    return "volatile"
```

Add `LAI_EMA_CEILING` to the existing import from `config` at the top of
`generator.py`. Check if it's already imported — if not, add it.

### 2B — Rewrite `_get_cdt_modifier()` in generator.py

**File:** `modules/feedback/generator.py`

Replace the existing `_get_cdt_modifier()` function entirely with this
upgraded version:

```python
def _get_cdt_modifier(
    db_session: Session,
    user_id: int,
    session_id: str,
    bias_type: str,
    current_severity: str,
    profile: CognitiveProfile,
) -> str:
    """Generate a CDT-aware contextual sentence appended to feedback explanation.

    Uses 3-session trajectory analysis when ≥ 3 prior sessions exist.
    Falls back to single-lag comparison for exactly 2 prior sessions.
    Returns empty string when fewer than 3 total sessions are completed
    or when no notable trend or stability pattern is detected.

    Args:
        db_session:       Active SQLAlchemy session.
        user_id:          ID of the user.
        session_id:       Current session UUID (excluded from prior-metric queries).
        bias_type:        One of "overconfidence", "disposition_effect", "loss_aversion".
        current_severity: Severity label for this session.
        profile:          Current CognitiveProfile.

    Returns:
        A Bahasa Indonesia modifier string, or "".
    """
    if profile.session_count < 3:
        return ""

    modifiers: list[str] = []

    # --- 3-session trajectory analysis ---
    trajectory = _classify_bias_trajectory(
        db_session, user_id, session_id, bias_type
    )

    if trajectory == "improving" and current_severity != "none":
        modifiers.append(
            "Tren positif terdeteksi: intensitas bias ini menurun secara konsisten "
            "dalam 3 sesi terakhir — umpan balik yang kamu terima menunjukkan dampak."
        )
    elif trajectory == "improving" and current_severity == "none":
        modifiers.append(
            "Tren positif terdeteksi: bias ini tidak lagi signifikan setelah menurun "
            "secara konsisten dalam 3 sesi terakhir. Pertahankan pola ini!"
        )
    elif trajectory == "worsening":
        modifiers.append(
            "Perhatian: intensitas bias ini meningkat secara konsisten dalam 3 sesi "
            "terakhir. Tinjau kembali strategi keputusan investasimu secara mendasar."
        )
    elif trajectory == "volatile":
        modifiers.append(
            "Pola tidak konsisten: bias ini berfluktuasi antar sesi, mengindikasikan "
            "bahwa keputusanmu mungkin dipengaruhi oleh kondisi pasar sesi tertentu "
            "daripada pola perilaku yang menetap."
        )
    elif trajectory == "insufficient":
        # Fewer than 3 prior sessions — fall back to single-lag comparison
        prev_feedback = (
            db_session.query(FeedbackHistory)
            .filter_by(user_id=user_id, bias_type=bias_type)
            .filter(FeedbackHistory.session_id != session_id)
            .order_by(FeedbackHistory.delivered_at.desc())
            .first()
        )
        if prev_feedback:
            curr_rank = _SEVERITY_RANK.get(current_severity, 0)
            prev_rank = _SEVERITY_RANK.get(prev_feedback.severity, 0)
            if curr_rank < prev_rank and current_severity != "none":
                modifiers.append(
                    "Perkembangan positif: kecenderungan bias ini menurun dibanding "
                    "sesi sebelumnya."
                )
            elif curr_rank > prev_rank:
                modifiers.append(
                    "Perhatian: intensitas bias ini meningkat dari sesi sebelumnya."
                )
    # trajectory == "stable": no modifier needed (no trend to report)

    # --- Persistent-pattern warning (independent of trajectory) ---
    if (
        profile.stability_index > CDT_MODIFIER_STABILITY_THRESHOLD
        and current_severity in ("moderate", "severe")
    ):
        modifiers.append(
            "Pola ini terdeteksi konsisten di beberapa sesi terakhir — "
            "pertimbangkan untuk mengubah strategi tradingmu secara lebih mendasar."
        )

    return " ".join(modifiers)
```

---

## TASK 3 — Write Tests

### 3A — New test file: `tests/test_cdt_elevation.py`

Create this file from scratch. It tests both the interaction modifier (V2)
and the trajectory classifier (V3).

**File:** `tests/test_cdt_elevation.py`

```python
"""
tests/test_cdt_elevation.py — Tests for CDT elevation features.

Covers:
    - _get_interaction_modifier() — cross-bias coupling insights
    - _classify_bias_trajectory() — 3-session trend classifier
    - _get_cdt_modifier() — upgraded trajectory-aware modifier
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import (
    Base, BiasMetric, CognitiveProfile, FeedbackHistory, User,
)
from modules.cdt.profile import get_or_create_profile
from modules.feedback.generator import (
    _classify_bias_trajectory,
    _get_cdt_modifier,
    _get_interaction_modifier,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    sess = Session()
    yield sess
    sess.close()


@pytest.fixture()
def user(db):
    u = User(alias="elevation_test_user", experience_level="beginner")
    db.add(u)
    db.flush()
    return u


def _add_bias_metric(db, user_id, ocs=0.0, dei=0.0, lai=1.0, days_ago=0):
    """Helper: insert a BiasMetric with a backdated computed_at."""
    sid = str(uuid.uuid4())
    m = BiasMetric(
        user_id=user_id,
        session_id=sid,
        overconfidence_score=ocs,
        disposition_pgr=max(dei, 0.0),
        disposition_plr=0.0,
        disposition_dei=dei,
        loss_aversion_index=lai,
        computed_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )
    db.add(m)
    db.flush()
    return m


def _add_feedback(db, user_id, session_id, bias_type, severity, days_ago=0):
    """Helper: insert a FeedbackHistory record."""
    fh = FeedbackHistory(
        user_id=user_id,
        session_id=session_id,
        bias_type=bias_type,
        severity=severity,
        explanation_text=f"Test explanation for {bias_type}",
        recommendation_text="Test recommendation",
        delivered_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )
    db.add(fh)
    db.flush()
    return fh


# ---------------------------------------------------------------------------
# Tests: _get_interaction_modifier()
# ---------------------------------------------------------------------------

class _FakeProfile:
    """Minimal profile-like object for testing _get_interaction_modifier."""
    def __init__(self, session_count, interaction_scores):
        self.session_count = session_count
        self.interaction_scores = interaction_scores
        self.stability_index = 0.5


def test_interaction_modifier_returns_empty_below_session_threshold():
    """Fewer than 5 sessions → no insights regardless of correlation."""
    profile = _FakeProfile(
        session_count=4,
        interaction_scores={"ocs_dei": 0.9, "ocs_lai": 0.8, "dei_lai": 0.7},
    )
    result = _get_interaction_modifier(profile)
    assert result == []


def test_interaction_modifier_returns_empty_when_no_scores():
    """interaction_scores is None → no insights."""
    profile = _FakeProfile(session_count=6, interaction_scores=None)
    assert _get_interaction_modifier(profile) == []


def test_interaction_modifier_returns_empty_below_threshold():
    """All correlations below 0.65 → no insights."""
    profile = _FakeProfile(
        session_count=6,
        interaction_scores={"ocs_dei": 0.4, "ocs_lai": 0.3, "dei_lai": 0.5},
    )
    assert _get_interaction_modifier(profile) == []


def test_interaction_modifier_high_ocs_dei():
    """OCS-DEI r = 0.80 → insight about overtrading + premature winner selling."""
    profile = _FakeProfile(
        session_count=6,
        interaction_scores={"ocs_dei": 0.80, "ocs_lai": None, "dei_lai": None},
    )
    insights = _get_interaction_modifier(profile)
    assert len(insights) == 1
    assert "overconfidence" in insights[0].lower() or "disposisi" in insights[0].lower()


def test_interaction_modifier_high_dei_lai_positive():
    """DEI-LAI r = 0.70 → insight about dual reinforcing biases."""
    profile = _FakeProfile(
        session_count=7,
        interaction_scores={"ocs_dei": None, "ocs_lai": None, "dei_lai": 0.70},
    )
    insights = _get_interaction_modifier(profile)
    assert len(insights) == 1
    # Should mention both biases reinforcing each other
    text = insights[0].lower()
    assert "memperkuat" in text or "bersamaan" in text


def test_interaction_modifier_negative_correlation_compensatory():
    """OCS-LAI r = -0.70 → compensatory pattern insight."""
    profile = _FakeProfile(
        session_count=6,
        interaction_scores={"ocs_dei": None, "ocs_lai": -0.70, "dei_lai": None},
    )
    insights = _get_interaction_modifier(profile)
    assert len(insights) == 1
    assert "kompensasi" in insights[0].lower()


def test_interaction_modifier_multiple_strong_correlations():
    """Two strong correlations → two separate insights."""
    profile = _FakeProfile(
        session_count=6,
        interaction_scores={"ocs_dei": 0.75, "ocs_lai": None, "dei_lai": 0.80},
    )
    insights = _get_interaction_modifier(profile)
    assert len(insights) == 2


def test_interaction_modifier_exactly_at_threshold():
    """OCS-DEI r = 0.65 (boundary) → insight IS returned (>= threshold)."""
    profile = _FakeProfile(
        session_count=5,
        interaction_scores={"ocs_dei": 0.65, "ocs_lai": None, "dei_lai": None},
    )
    insights = _get_interaction_modifier(profile)
    assert len(insights) == 1


def test_interaction_modifier_just_below_threshold():
    """OCS-DEI r = 0.64 (just below boundary) → no insight."""
    profile = _FakeProfile(
        session_count=5,
        interaction_scores={"ocs_dei": 0.64, "ocs_lai": None, "dei_lai": None},
    )
    assert _get_interaction_modifier(profile) == []


# ---------------------------------------------------------------------------
# Tests: _classify_bias_trajectory()
# ---------------------------------------------------------------------------

def test_trajectory_improving_overconfidence(db, user):
    """3 prior sessions with strictly decreasing OCS → 'improving'."""
    # oldest → newest: 0.8 → 0.5 → 0.3 (strictly decreasing)
    _add_bias_metric(db, user.id, ocs=0.8, days_ago=4)
    _add_bias_metric(db, user.id, ocs=0.5, days_ago=3)
    _add_bias_metric(db, user.id, ocs=0.3, days_ago=2)
    current_sid = str(uuid.uuid4())

    result = _classify_bias_trajectory(db, user.id, current_sid, "overconfidence")
    assert result == "improving"


def test_trajectory_worsening_disposition(db, user):
    """3 prior sessions with strictly increasing |DEI| → 'worsening'."""
    _add_bias_metric(db, user.id, dei=0.1, days_ago=4)
    _add_bias_metric(db, user.id, dei=0.2, days_ago=3)
    _add_bias_metric(db, user.id, dei=0.4, days_ago=2)
    current_sid = str(uuid.uuid4())

    result = _classify_bias_trajectory(db, user.id, current_sid, "disposition_effect")
    assert result == "worsening"


def test_trajectory_stable_loss_aversion(db, user):
    """3 prior sessions with LAI within 0.05 band → 'stable'."""
    # normalized: min(1.5/3, 1) = 0.5, min(1.52/3, 1) ≈ 0.507, min(1.48/3, 1) ≈ 0.493
    _add_bias_metric(db, user.id, lai=1.5, days_ago=4)
    _add_bias_metric(db, user.id, lai=1.52, days_ago=3)
    _add_bias_metric(db, user.id, lai=1.48, days_ago=2)
    current_sid = str(uuid.uuid4())

    result = _classify_bias_trajectory(db, user.id, current_sid, "loss_aversion")
    assert result == "stable"


def test_trajectory_volatile_pattern(db, user):
    """Non-monotonic pattern → 'volatile'."""
    # 0.2 → 0.6 → 0.3 (up then down, not monotonic)
    _add_bias_metric(db, user.id, ocs=0.2, days_ago=4)
    _add_bias_metric(db, user.id, ocs=0.6, days_ago=3)
    _add_bias_metric(db, user.id, ocs=0.3, days_ago=2)
    current_sid = str(uuid.uuid4())

    result = _classify_bias_trajectory(db, user.id, current_sid, "overconfidence")
    assert result == "volatile"


def test_trajectory_insufficient_two_prior(db, user):
    """Only 2 prior sessions → 'insufficient'."""
    _add_bias_metric(db, user.id, ocs=0.5, days_ago=3)
    _add_bias_metric(db, user.id, ocs=0.3, days_ago=2)
    current_sid = str(uuid.uuid4())

    result = _classify_bias_trajectory(db, user.id, current_sid, "overconfidence")
    assert result == "insufficient"


def test_trajectory_insufficient_zero_prior(db, user):
    """No prior sessions → 'insufficient'."""
    current_sid = str(uuid.uuid4())
    result = _classify_bias_trajectory(db, user.id, current_sid, "overconfidence")
    assert result == "insufficient"


def test_trajectory_excludes_current_session(db, user):
    """Current session metrics must NOT be counted as prior sessions."""
    _add_bias_metric(db, user.id, ocs=0.8, days_ago=4)
    _add_bias_metric(db, user.id, ocs=0.6, days_ago=3)

    # Third metric IS the current session — should be excluded
    current_metric = _add_bias_metric(db, user.id, ocs=0.1, days_ago=0)

    result = _classify_bias_trajectory(
        db, user.id, current_metric.session_id, "overconfidence"
    )
    # Only 2 prior sessions available after excluding current → insufficient
    assert result == "insufficient"


def test_trajectory_uses_last_three_of_many(db, user):
    """When 5 prior sessions exist, only the most recent 3 should be used."""
    # Sessions (oldest→newest): 0.9, 0.8, 0.7, 0.5, 0.3 — last 3 are 0.7→0.5→0.3 (improving)
    _add_bias_metric(db, user.id, ocs=0.9, days_ago=6)
    _add_bias_metric(db, user.id, ocs=0.8, days_ago=5)
    _add_bias_metric(db, user.id, ocs=0.7, days_ago=4)
    _add_bias_metric(db, user.id, ocs=0.5, days_ago=3)
    _add_bias_metric(db, user.id, ocs=0.3, days_ago=2)
    current_sid = str(uuid.uuid4())

    result = _classify_bias_trajectory(db, user.id, current_sid, "overconfidence")
    assert result == "improving"


# ---------------------------------------------------------------------------
# Tests: _get_cdt_modifier() integration
# ---------------------------------------------------------------------------

def test_cdt_modifier_improving_trajectory_generates_positive_text(db, user):
    """Improving trajectory → modifier contains positive Bahasa Indonesia text."""
    _add_bias_metric(db, user.id, ocs=0.8, days_ago=4)
    _add_bias_metric(db, user.id, ocs=0.5, days_ago=3)
    _add_bias_metric(db, user.id, ocs=0.3, days_ago=2)

    profile = get_or_create_profile(db, user.id)
    profile.session_count = 4  # simulate 4+ sessions
    db.flush()

    current_sid = str(uuid.uuid4())
    result = _get_cdt_modifier(db, user.id, current_sid, "overconfidence", "mild", profile)

    assert result != ""
    assert "positif" in result.lower() or "menurun" in result.lower()


def test_cdt_modifier_worsening_trajectory_generates_warning(db, user):
    """Worsening trajectory → modifier contains warning text."""
    _add_bias_metric(db, user.id, ocs=0.2, days_ago=4)
    _add_bias_metric(db, user.id, ocs=0.4, days_ago=3)
    _add_bias_metric(db, user.id, ocs=0.7, days_ago=2)

    profile = get_or_create_profile(db, user.id)
    profile.session_count = 4
    db.flush()

    current_sid = str(uuid.uuid4())
    result = _get_cdt_modifier(db, user.id, current_sid, "overconfidence", "severe", profile)

    assert result != ""
    assert "perhatian" in result.lower() or "meningkat" in result.lower()


def test_cdt_modifier_below_session_threshold_returns_empty(db, user):
    """session_count < 3 → always returns empty string."""
    profile = get_or_create_profile(db, user.id)
    profile.session_count = 2
    db.flush()

    current_sid = str(uuid.uuid4())
    result = _get_cdt_modifier(db, user.id, current_sid, "overconfidence", "moderate", profile)
    assert result == ""


def test_cdt_modifier_stable_trajectory_returns_empty_for_mild(db, user):
    """Stable trajectory + mild severity → no modifier (nothing actionable)."""
    _add_bias_metric(db, user.id, ocs=0.3, days_ago=4)
    _add_bias_metric(db, user.id, ocs=0.31, days_ago=3)
    _add_bias_metric(db, user.id, ocs=0.29, days_ago=2)

    profile = get_or_create_profile(db, user.id)
    profile.session_count = 4
    db.flush()

    current_sid = str(uuid.uuid4())
    result = _get_cdt_modifier(db, user.id, current_sid, "overconfidence", "mild", profile)
    # Stable + mild → no trajectory modifier; no stability warning (stability_index = 0.0 < 0.75)
    assert result == ""


def test_cdt_modifier_stability_warning_appended(db, user):
    """High stability_index + moderate severity → stability warning appended."""
    _add_bias_metric(db, user.id, ocs=0.5, days_ago=4)
    _add_bias_metric(db, user.id, ocs=0.52, days_ago=3)
    _add_bias_metric(db, user.id, ocs=0.49, days_ago=2)

    profile = get_or_create_profile(db, user.id)
    profile.session_count = 5
    profile.stability_index = 0.85  # above CDT_MODIFIER_STABILITY_THRESHOLD (0.75)
    db.flush()

    current_sid = str(uuid.uuid4())
    result = _get_cdt_modifier(db, user.id, current_sid, "overconfidence", "moderate", profile)
    # Stable trajectory + high stability + moderate severity → stability warning
    assert "konsisten" in result.lower() or "strategi" in result.lower()


def test_cdt_modifier_insufficient_falls_back_to_single_lag(db, user):
    """With only 2 prior sessions, falls back to single-lag FeedbackHistory comparison."""
    m1 = _add_bias_metric(db, user.id, ocs=0.6, days_ago=3)
    _add_feedback(db, user.id, m1.session_id, "overconfidence", "moderate", days_ago=3)

    profile = get_or_create_profile(db, user.id)
    profile.session_count = 3  # 3 total, but only 1 prior BiasMetric
    db.flush()

    current_sid = str(uuid.uuid4())
    # Current severity "mild" < previous "moderate" → positive feedback
    result = _get_cdt_modifier(db, user.id, current_sid, "overconfidence", "mild", profile)
    assert "positif" in result.lower() or "menurun" in result.lower()
```

---

## TASK 4 — Run Full Test Suite

After completing all changes:

```bash
pytest tests/ -v --tb=short
```

**Target:** All existing tests pass + all new tests in `test_cdt_elevation.py`
pass. Zero failures permitted.

If any existing test fails due to the modifier changes, investigate:
- Check if the test was asserting on the exact content of `explanation_text`
  that may now include a trajectory modifier suffix.
- If so, update the assertion to use `assert "expected_fragment" in fb.explanation_text`
  instead of equality checks.
- Do NOT loosen assertions beyond this.

---

## VERIFICATION CHECKLIST

After `pytest tests/ -v` shows 0 failures, verify manually:

### Interaction Synthesis (V2)
- [ ] Log in, complete 5 full sessions (minimum for V2 to trigger)
- [ ] On the feedback page after session 5+, a "🔗 Pola Bias Gabungan" section
      appears **only if** at least one Pearson r ≥ 0.65
- [ ] If no strong coupling exists, the section does NOT appear
- [ ] The section appears AFTER the longitudinal strip, BEFORE the navigation CTAs
- [ ] The section appears BEFORE the PostSessionSurvey (which is the last element)

### Trajectory Modifier (V3)
- [ ] After 3 completed sessions, the bias cards include trajectory text
      ("Tren positif" or "Perhatian: intensitas... meningkat secara konsisten")
- [ ] After only 2 sessions, the modifier falls back to single-lag comparison
      ("Perkembangan positif" or "Perhatian: intensitas...meningkat dari sesi sebelumnya")
- [ ] After 1 session, no modifier appears
- [ ] A "volatile" pattern shows "berfluktuasi" text
- [ ] Stable + mild severity: no modifier (correct — nothing to report)
- [ ] High stability_index (≥0.75) + moderate/severe: stability warning always
      appended regardless of trajectory

### Regression
- [ ] PostSessionSurvey still appears at the bottom of the feedback page ✓
- [ ] All 3 bias cards still render correctly ✓
- [ ] Longitudinal strip still appears ✓
- [ ] Session navigation CTAs (Mulai Sesi Baru / Profil Kognitif) still work ✓

---

## THESIS ALIGNMENT NOTES

Document these additions in **Bab V — Implementasi**:

1. **Skor Interaksi Antar-Bias (V2):**
   "Sistem menghitung korelasi Pearson antara ketiga bias menggunakan data
   multi-sesi (minimum 5 sesi). Jika |r| ≥ 0,65, sistem menampilkan wawasan
   gabungan yang mengidentifikasi pola perilaku yang saling memperkuat atau
   saling mengimbangi. Ini merupakan implementasi dari sifat *coupled* pada
   model Cognitive Digital Twin."

2. **Pengklasifikasi Trajektori 3-Sesi (V3):**
   "Modul umpan balik CDT diperbarui dengan analisis tren 3-sesi yang
   mengklasifikasikan trajektori bias sebagai *improving*, *worsening*,
   *volatile*, atau *stable*. Ini memberikan sinyal yang lebih kaya daripada
   perbandingan sesi tunggal, dan secara langsung mendukung klaim mitigasi
   dalam judul tugas akhir ini: penurunan konsisten dalam 3 sesi merupakan
   bukti indikatif bahwa umpan balik CDT mendorong perubahan perilaku."

Document in **Bab VI — Evaluasi**, subsection "Analisis Longitudinal":
   "Jika trajektori bias partisipan menunjukkan klasifikasi *improving* dalam
   sesi ke-3 atau selanjutnya, ini dicatat sebagai indikasi awal efek mitigasi.
   Sistem secara eksplisit mengkomunikasikan tren ini kepada pengguna."
