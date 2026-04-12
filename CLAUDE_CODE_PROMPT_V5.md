# CLAUDE CODE IMPLEMENTATION PROMPT — V5
## CDT Bias Detection System | TA-18222007 | ITB

---

## CONTEXT & SCOPE

This prompt covers three UX bug fixes confirmed by direct simulation experience, and three
Nice-to-Have feature additions. V4 was executed completely and correctly — no remediation
needed. All V5 tasks are net-new changes to the post-V4 codebase.

**Do NOT** alter bias formulas, test fixtures in conftest.py, existing V4 tests, or any
module not explicitly named per task. Run `pytest tests/ -v` after all tasks are complete
and ensure the suite passes with 0 failures.

---

## TASK A — FIX: Authentication Loop (app.py)

### Problem
`_page_beranda()` renders the login form section unconditionally. After login, the user's
`user_id` is set in session state and `st.rerun()` is called, but Streamlit re-renders the
same Beranda page — and the login form re-appears below the dashboard. The user sees both
their session history AND the login form simultaneously.

### Root Cause
`modules/app.py` lines ~291–373 — the block starting with `st.divider()` /
`st.subheader("Login / Daftar")` and the survey form are not guarded by `if not user_id:`.

### Fix — app.py

**In `_page_beranda()`**, locate the section that begins with:
```python
    st.divider()
    st.subheader("Login / Daftar")
```

And wrap EVERYTHING from that `st.divider()` line through the end of the survey form
(`if survey_skipped:` block) inside `if not user_id:`. The entire login + survey block
is only relevant when the user is not yet authenticated.

**Exact replacement** — replace this block:

```python
    st.divider()
    st.subheader("Login / Daftar")

    with st.form("login_form"):
```

with:

```python
    if not user_id:
        st.divider()
        st.subheader("Login / Daftar")

        with st.form("login_form"):
```

Then indent every line from `with st.form("login_form"):` to the final
`if survey_skipped:` block (including the survey expander) by **4 additional spaces** so
they sit inside the `if not user_id:` guard.

The `with st.expander("ℹ️ Bagaimana sistem ini bekerja?", ...)` block (which uses
`expanded=not bool(user_id)`) should remain OUTSIDE the guard — it is correctly displayed
for both logged-in and logged-out users.

### Expected Result
- Logged-in user on Beranda sees: CTA button → session history metrics → how-it-works expander.
- Login form is completely absent for authenticated users.
- Post-login redirect to Simulasi Investasi remains intact (lines inside the `if submitted:` handler are unchanged in logic).

---

## TASK B — FIX: Candlestick Chart Date Gaps (modules/simulation/ui.py)

### Problem
The candlestick chart shows irregular white gaps on non-trading days (weekends, public
holidays). The IDX market data has natural gaps in the date sequence. When Plotly renders
a time-series x-axis from date strings, it fills the missing calendar dates with blank
spaces.

### Root Cause
`_build_full_chart()` uses `d["date"].isoformat()` to build x-axis values — creating a
continuous date string sequence. Plotly treats these as a continuous time axis and inserts
visual gaps for missing dates.

### Fix — modules/simulation/ui.py

In `_build_full_chart()`, locate the final `fig.update_xaxes(...)` call near the bottom
of the function:

```python
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.08)")
```

Replace it with:

```python
    fig.update_xaxes(type="category", gridcolor="rgba(255,255,255,0.08)")
```

`type="category"` forces Plotly to treat x-axis values as discrete categories rather than
a continuous time axis. This eliminates all calendar-day gap filling and renders only the
dates that have actual data — matching exactly the 14 trading-day window.

**No other changes** to `_build_full_chart()` are needed. The date-to-string conversion
logic (`.isoformat()`) remains unchanged — category mode works with any string type.

### Expected Result
- Candlestick bars are evenly spaced with no gaps.
- Pre-window history line is also gap-free.
- MA5/MA20 overlays align correctly with their corresponding candles.

---

## TASK C — FIX: Simulation Completion Flow (modules/simulation/ui.py + modules/feedback/renderer.py)

### Problem
After round 14 executes, the user is shown an intermediate "Sesi Selesai" screen and must
manually click "📊 Lihat Hasil Analisis →" to navigate to results. This creates unnecessary
friction. Additionally, once on the results page, there is no direct "Mulai Sesi Baru"
button — the user must navigate the sidebar or go through Beranda.

### Fix Part 1 — Auto-redirect after pipeline (modules/simulation/ui.py)

In `_execute_round()`, locate the block that runs the post-session pipeline:

```python
    if next_round > ROUNDS_PER_SESSION and not st.session_state.get("sim_complete"):
        st.session_state["sim_complete"] = True
        with st.spinner("Menganalisis keputusan investasi kamu…"):
            try:
                _run_post_session_pipeline(user_id, session_id)
            except Exception:
                st.error(
                    "Terjadi kesalahan saat menganalisis sesi. "
                    "Silakan hubungi administrator dengan kode sesi: "
                    f"{session_id[:8]}"
                )

    st.rerun()
```

Replace it with:

```python
    if next_round > ROUNDS_PER_SESSION and not st.session_state.get("sim_complete"):
        st.session_state["sim_complete"] = True
        with st.spinner("Menganalisis keputusan investasi kamu…"):
            try:
                _run_post_session_pipeline(user_id, session_id)
                # Pipeline succeeded — auto-redirect to results page.
                st.session_state["last_session_id"] = session_id
                st.session_state["current_page"] = "Hasil Analisis & Umpan Balik"
                reset_simulation()
                st.rerun()
            except Exception:
                st.error(
                    "Terjadi kesalahan saat menganalisis sesi. "
                    "Silakan hubungi administrator dengan kode sesi: "
                    f"{session_id[:8]}"
                )

    st.rerun()
```

The `reset_simulation()` call clears all sim state before the rerun, so the "Simulasi
Investasi" page will initialise fresh on the next visit. The `sim_complete` block in
`render_simulation_page()` (lines ~515–534) can remain as a fallback for the error path,
but will no longer be reached on the happy path.

### Fix Part 2 — "Mulai Sesi Baru" CTA on results page (modules/feedback/renderer.py)

In `render_feedback_page()`, add the following block at the **very end** of the function,
after the longitudinal section and before the function returns:

```python
    # --- Session navigation CTAs ---
    st.divider()
    col_new, col_profile = st.columns(2)
    with col_new:
        if st.button("🔄 Mulai Sesi Baru", use_container_width=True, type="primary"):
            st.session_state["current_page"] = "Simulasi Investasi"
            st.rerun()
    with col_profile:
        if st.button("🧠 Lihat Profil Kognitif →", use_container_width=True):
            st.session_state["current_page"] = "Profil Kognitif Saya"
            st.rerun()
```

You will need to add `import streamlit as st` at the top of renderer.py if not already
present (it is — it's already imported on line 1).

### Expected Result
- After round 14: spinner appears → pipeline runs → results page loads automatically.
- On results page: two CTA buttons at bottom — "Mulai Sesi Baru" and "Lihat Profil Kognitif".
- Error path: if pipeline fails, error message shows and user remains on simulation page.

---

## TASK D — FEATURE: Cross-Bias Interaction Score (N-01)

### Design
Compute pairwise Pearson correlation coefficients between the three bias metrics across a
user's last N sessions (up to CDT_STABILITY_WINDOW). This surfaces coupled patterns:
e.g., a user who simultaneously overtrades AND holds losers long (high OCS + high LAI
correlation) has a structurally compounded risk profile.

Requires ≥3 sessions. Returns `None` for each pair if insufficient data or if either
series has zero variance.

### Step D.1 — Add column to CognitiveProfile (database/models.py)

In `CognitiveProfile`, add a new column after `stability_index`:

```python
    # JSON: {"ocs_dei": float|null, "ocs_lai": float|null, "dei_lai": float|null}
    # Null values indicate insufficient data or zero-variance series.
    interaction_scores: Optional[dict] = Column(JSON, nullable=True, default=None)
```

The `Optional` type hint is already imported. No migration needed — SQLite handles new
nullable JSON columns transparently.

### Step D.2 — New module: modules/cdt/interaction.py

Create `/sessions/adoring-ecstatic-ptolemy/mnt/TA-18222007/modules/cdt/interaction.py`
with the following content:

```python
"""
modules/cdt/interaction.py — Cross-bias interaction score computation.

Computes pairwise Pearson correlation coefficients between OCS, |DEI|, and
normalised LAI across recent sessions, capturing coupled behavioral patterns.

Functions:
    compute_interaction_scores — Returns a dict of pairwise correlations.
"""

from __future__ import annotations

import math
from typing import Optional

from sqlalchemy.orm import Session

from config import CDT_STABILITY_WINDOW, LAI_EMA_CEILING
from database.models import BiasMetric

import logging

logger = logging.getLogger(__name__)

_MIN_SESSIONS_FOR_INTERACTION = 3


def _pearson(xs: list[float], ys: list[float]) -> Optional[float]:
    """Compute Pearson r between two equal-length series.

    Returns None if n < 2, or if either series has zero variance.
    """
    n = len(xs)
    if n < 2 or len(ys) != n:
        return None

    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (n - 1)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs) / (n - 1))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys) / (n - 1))

    if sx < 1e-9 or sy < 1e-9:
        return None  # zero-variance series → undefined correlation

    return max(-1.0, min(1.0, cov / (sx * sy)))  # clamp to [-1,1] for float safety


def compute_interaction_scores(
    db_session: Session, user_id: int
) -> Optional[dict]:
    """Compute pairwise Pearson correlations between bias metrics across sessions.

    Uses the last CDT_STABILITY_WINDOW sessions (same window as stability index).
    Returns None when fewer than _MIN_SESSIONS_FOR_INTERACTION sessions exist.

    Normalisation applied before correlation (same as stability index):
        - OCS: already in [0,1) — unchanged.
        - DEI: |DEI| (absolute value, capturing magnitude regardless of sign).
        - LAI: min(LAI / LAI_EMA_CEILING, 1.0).

    Returns:
        Dict with keys "ocs_dei", "ocs_lai", "dei_lai" — each a float in [-1,1]
        or None if either series has zero variance. Returns None if insufficient
        sessions.
    """
    metrics = (
        db_session.query(BiasMetric)
        .filter_by(user_id=user_id)
        .order_by(BiasMetric.computed_at.desc())
        .limit(CDT_STABILITY_WINDOW)
        .all()
    )

    if len(metrics) < _MIN_SESSIONS_FOR_INTERACTION:
        return None

    ocs_vals = [m.overconfidence_score or 0.0 for m in metrics]
    dei_vals = [abs(m.disposition_dei or 0.0) for m in metrics]
    lai_vals = [min((m.loss_aversion_index or 0.0) / LAI_EMA_CEILING, 1.0) for m in metrics]

    result = {
        "ocs_dei": _pearson(ocs_vals, dei_vals),
        "ocs_lai": _pearson(ocs_vals, lai_vals),
        "dei_lai": _pearson(dei_vals, lai_vals),
    }

    logger.debug(
        "user=%s interaction_scores: ocs_dei=%.3f ocs_lai=%.3f dei_lai=%.3f",
        user_id,
        result["ocs_dei"] if result["ocs_dei"] is not None else float("nan"),
        result["ocs_lai"] if result["ocs_lai"] is not None else float("nan"),
        result["dei_lai"] if result["dei_lai"] is not None else float("nan"),
    )
    return result
```

### Step D.3 — Update updater.py to compute and store interaction scores

In `modules/cdt/updater.py`:

**Add import** at the top (after the existing CDT imports):
```python
from modules.cdt.interaction import compute_interaction_scores
```

**In `update_profile()`**, after the line `profile.stability_index = compute_stability_index(db_session, user_id)`, add:
```python
    profile.interaction_scores = compute_interaction_scores(db_session, user_id)
```

### Step D.4 — Display in Profil Kognitif page (app.py)

In `_page_profil()`, after the "Session history line chart" block (the `if len(metrics_data) >= 2:` section), and BEFORE the "Insight" section, add:

```python
    # --- Cross-Bias Interaction Scores ---
    interaction = profile_data.get("interaction_scores")
    if interaction:
        st.subheader("🔗 Interaksi Antar Bias")
        st.caption(
            "Korelasi Pearson antara bias-biasmu. Nilai mendekati +1 berarti dua bias "
            "sering muncul bersamaan; mendekati -1 berarti saling berlawanan."
        )

        def _fmt_corr(v) -> str:
            if v is None:
                return "—"
            bar = "█" * int(abs(v) * 10)
            direction = "+" if v >= 0 else "−"
            return f"{direction}{abs(v):.2f} {bar}"

        ic1, ic2, ic3 = st.columns(3)
        ic1.metric(
            "OCS ↔ |DEI|",
            _fmt_corr(interaction.get("ocs_dei")),
            help="Korelasi antara Overconfidence dan Efek Disposisi",
            delta=" ", delta_color="off",
        )
        ic2.metric(
            "OCS ↔ LAI",
            _fmt_corr(interaction.get("ocs_lai")),
            help="Korelasi antara Overconfidence dan Loss Aversion",
            delta=" ", delta_color="off",
        )
        ic3.metric(
            "│DEI│ ↔ LAI",
            _fmt_corr(interaction.get("dei_lai")),
            help="Korelasi antara Efek Disposisi dan Loss Aversion",
            delta=" ", delta_color="off",
        )

        # Narrative interpretation for the strongest pair
        valid_pairs = {k: v for k, v in interaction.items() if v is not None}
        if valid_pairs:
            strongest_pair = max(valid_pairs, key=lambda k: abs(valid_pairs[k]))
            val = valid_pairs[strongest_pair]
            pair_names = {
                "ocs_dei": "Overconfidence dan Efek Disposisi",
                "ocs_lai": "Overconfidence dan Loss Aversion",
                "dei_lai": "Efek Disposisi dan Loss Aversion",
            }
            if abs(val) >= 0.6:
                direction = "cenderung muncul bersamaan" if val > 0 else "saling berlawanan"
                st.info(
                    f"💡 **{pair_names[strongest_pair]}** {direction} (r={val:+.2f}). "
                    f"Ini menunjukkan pola perilaku yang saling terkait pada profilmu."
                )
```

**Also update `profile_data` dict** (in `_page_profil()`) to include `interaction_scores`:
```python
        profile_data = {
            "bias_vector": dict(profile.bias_intensity_vector),
            "risk_preference": profile.risk_preference,
            "stability_index": profile.stability_index,
            "session_count": profile.session_count,
            "last_updated_at": profile.last_updated_at,
            "interaction_scores": profile.interaction_scores,  # ADD THIS LINE
        }
```

---

## TASK E — FEATURE: Isolation Forest ML Anomaly Validation (N-02)

### Design
An unsupervised Isolation Forest flags sessions whose bias profile is anomalous relative
to the user's own history. This is not about "good vs. bad" bias — it's about detecting
sessions that are structurally unusual (e.g., an normally conservative user suddenly
overtrades). Requires ≥5 sessions. Displayed as a "behavioral consistency" panel on the
Profil Kognitif page.

scikit-learn is used for the Isolation Forest. It must be a soft dependency: if
`sklearn` is not installed, the feature silently degrades to None.

### Step E.1 — New module: modules/cdt/ml_validator.py

Create `/sessions/adoring-ecstatic-ptolemy/mnt/TA-18222007/modules/cdt/ml_validator.py`:

```python
"""
modules/cdt/ml_validator.py — Isolation Forest anomaly detection for CDT validation.

Validates the CDT bias detection system (FR02 support) by applying an unsupervised
Isolation Forest to the user's session-level bias scores. Sessions whose bias vectors
deviate significantly from the user's own behavioral baseline are flagged as anomalous.

This provides a lightweight ML validation layer without supervised labels, consistent
with the small-sample constraints of the thesis UAT (N ≈ 10–15 participants).

Functions:
    compute_anomaly_flags — Returns per-session anomaly scores and flag labels.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from config import LAI_EMA_CEILING
from database.models import BiasMetric

logger = logging.getLogger(__name__)

_MIN_SESSIONS_FOR_ML = 5
_ISOLATION_FOREST_CONTAMINATION = 0.1  # assume ~10% of sessions are structural outliers


def compute_anomaly_flags(
    db_session: Session, user_id: int
) -> Optional[dict]:
    """Apply Isolation Forest to the user's bias history to detect anomalous sessions.

    Features per session (all normalised to [0,1]):
        - OCS (already in [0,1))
        - |DEI| (absolute value)
        - LAI_norm = min(LAI / LAI_EMA_CEILING, 1.0)

    Args:
        db_session: Active SQLAlchemy session.
        user_id:    ID of the user.

    Returns:
        Dict with keys:
            "session_ids":    List[str] — session UUIDs in chronological order.
            "anomaly_scores": List[float] — Isolation Forest anomaly scores.
                              More negative = more anomalous (sklearn convention).
            "is_anomaly":     List[bool] — True if score < 0 (sklearn flags as outlier).
            "n_sessions":     int — number of sessions used.
        Returns None if sklearn unavailable, or fewer than _MIN_SESSIONS_FOR_ML sessions.
    """
    try:
        from sklearn.ensemble import IsolationForest
    except ImportError:
        logger.warning("scikit-learn not installed — ML anomaly detection unavailable.")
        return None

    metrics = (
        db_session.query(BiasMetric)
        .filter_by(user_id=user_id)
        .order_by(BiasMetric.computed_at)
        .all()
    )

    if len(metrics) < _MIN_SESSIONS_FOR_ML:
        return None

    X = [
        [
            m.overconfidence_score or 0.0,
            abs(m.disposition_dei or 0.0),
            min((m.loss_aversion_index or 0.0) / LAI_EMA_CEILING, 1.0),
        ]
        for m in metrics
    ]

    try:
        clf = IsolationForest(
            contamination=_ISOLATION_FOREST_CONTAMINATION,
            random_state=42,
            n_estimators=100,
        )
        clf.fit(X)
        raw_scores = clf.score_samples(X).tolist()   # more negative = more anomalous
        predictions = clf.predict(X).tolist()         # -1 = anomaly, 1 = normal
        is_anomaly = [p == -1 for p in predictions]
    except Exception as exc:
        logger.warning("IsolationForest failed: %s", exc)
        return None

    result = {
        "session_ids": [m.session_id for m in metrics],
        "anomaly_scores": raw_scores,
        "is_anomaly": is_anomaly,
        "n_sessions": len(metrics),
    }
    anomaly_count = sum(is_anomaly)
    logger.debug(
        "user=%s IsolationForest: %d sessions, %d anomalous",
        user_id, len(metrics), anomaly_count,
    )
    return result
```

### Step E.2 — Display in Profil Kognitif page (app.py)

In `_page_profil()`, add the following block **inside the `with get_session() as sess:` block** (where `profile` and `past_metrics` are already queried) to fetch ML anomaly data:

In the serialization block after `profile_data = {...}`, add:

```python
        # Fetch ML anomaly flags (requires sklearn; silently degrades)
        from modules.cdt.ml_validator import compute_anomaly_flags
        anomaly_data = compute_anomaly_flags(sess, user_id)
```

Then in the rendering section, **after the interaction scores block and before the Insight section**, add:

```python
    # --- ML Anomaly Detection Panel ---
    if anomaly_data:
        st.subheader("🤖 Deteksi Sesi Anomali (ML)")
        n = anomaly_data["n_sessions"]
        n_anomaly = sum(anomaly_data["is_anomaly"])
        st.caption(
            f"Isolation Forest dijalankan pada {n} sesi. "
            f"Sesi yang strukturnya menyimpang dari baseline perilakumu ditandai sebagai anomali."
        )

        if n_anomaly == 0:
            st.success(
                "✅ Tidak ada sesi anomali terdeteksi — pola biasmu konsisten di semua sesi."
            )
        else:
            st.warning(
                f"⚠️ {n_anomaly} dari {n} sesi menunjukkan profil bias yang tidak biasa. "
                f"Ini bisa berarti kamu bereksperimen dengan strategi berbeda, "
                f"atau kondisi pasar mendorong perilaku yang tidak khas."
            )

        # Per-session anomaly table
        import pandas as pd
        rows = []
        for i, (sid, score, flag) in enumerate(
            zip(
                anomaly_data["session_ids"],
                anomaly_data["anomaly_scores"],
                anomaly_data["is_anomaly"],
            )
        ):
            rows.append({
                "Sesi": f"#{i + 1}",
                "Anomali": "⚠️ Ya" if flag else "✅ Normal",
                "Skor": f"{score:.3f}",
                "ID (8 digit)": sid[:8],
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
    elif profile_data["session_count"] > 0:
        # Show teaser if sessions exist but not enough for ML
        from modules.cdt.ml_validator import _MIN_SESSIONS_FOR_ML
        remaining = _MIN_SESSIONS_FOR_ML - profile_data["session_count"]
        if remaining > 0:
            st.caption(
                f"🤖 Deteksi anomali ML tersedia setelah {_MIN_SESSIONS_FOR_ML} sesi "
                f"(butuh {remaining} sesi lagi)."
            )
```

**Note:** `pandas` is already used elsewhere in the project. Import it locally to avoid
polluting the module-level namespace for an optional block.

---

## TASK F — FEATURE: Post-UAT Self-Assessment Survey (N-03)

### Design
After the feedback page is rendered and the user has seen their bias scores, offer a brief
3-question self-assessment asking them to rate their own awareness of each bias BEFORE
seeing the results. This provides a "self vs. system" comparison for thesis analysis and
tests whether CDT feedback improves metacognitive awareness over sessions.

The survey shows once per session (after feedback is viewed) and cannot be resubmitted.

### Step F.1 — New ORM model (database/models.py)

Add the `PostSessionSurvey` class at the **end of `models.py`**, after `CdtSnapshot`:

```python
class PostSessionSurvey(Base):
    """Post-session self-assessment survey: user's self-rated bias awareness.

    Captured after the feedback page is viewed so responses reflect post-feedback
    metacognition. Compared against system-detected severity for thesis analysis.
    """

    __tablename__ = "post_session_surveys"
    __table_args__ = (
        UniqueConstraint("user_id", "session_id", name="uq_post_survey_user_session"),
    )

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    user_id: int = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id: str = Column(String(36), nullable=False)

    # Self-assessed bias awareness: 1 = tidak menyadari sama sekali, 5 = sangat menyadari
    self_overconfidence: int = Column(Integer, nullable=False)
    self_disposition: int = Column(Integer, nullable=False)
    self_loss_aversion: int = Column(Integer, nullable=False)

    # Overall feedback usefulness: 1 = tidak berguna, 5 = sangat berguna
    feedback_usefulness: int = Column(Integer, nullable=False)

    submitted_at: datetime = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return (
            f"<PostSessionSurvey user={self.user_id} session={self.session_id[:8]} "
            f"OC={self.self_overconfidence} DEI={self.self_disposition} LA={self.self_loss_aversion}>"
        )
```

### Step F.2 — Render survey in feedback page (modules/feedback/renderer.py)

At the **end of `render_feedback_page()`** (after the "Mulai Sesi Baru" CTA buttons added
in TASK C), add:

```python
    # --- Post-Session Self-Assessment Survey ---
    _render_post_session_survey(user_id=user_id, session_id=session_id)
```

Then add the following helper function **below** `render_feedback_page()` in the same file:

```python
def _render_post_session_survey(user_id: int, session_id: str) -> None:
    """Render the post-session self-assessment survey if not yet submitted.

    Shows a 4-question Likert survey capturing self-assessed bias awareness
    and feedback usefulness. Persisted as PostSessionSurvey in the database.
    Idempotent — does not re-render if already submitted for this session.
    """
    from database.models import PostSessionSurvey

    # Check if already submitted for this session
    with get_session() as check_sess:
        already_submitted = (
            check_sess.query(PostSessionSurvey)
            .filter_by(user_id=user_id, session_id=session_id)
            .first()
        ) is not None

    if already_submitted:
        st.caption("✅ Survei evaluasi diri untuk sesi ini sudah diisi. Terima kasih!")
        return

    st.divider()
    with st.expander("📝 Evaluasi Diri: Seberapa Menyadari Kamu Biasmu?", expanded=True):
        st.caption(
            "Jawab pertanyaan berikut berdasarkan perasaanmu **sebelum** melihat hasil "
            "analisis di atas. Jawaban kamu membantu penelitian ini memahami seberapa "
            "efektif umpan balik CDT dalam meningkatkan kesadaran diri investor."
        )

        LIKERT = {
            1: "1 — Tidak menyadari sama sekali",
            2: "2 — Sedikit menyadari",
            3: "3 — Cukup menyadari",
            4: "4 — Menyadari",
            5: "5 — Sangat menyadari",
        }
        USEFULNESS = {
            1: "1 — Tidak berguna",
            2: "2 — Kurang berguna",
            3: "3 — Cukup berguna",
            4: "4 — Berguna",
            5: "5 — Sangat berguna",
        }

        with st.form(f"post_survey_{session_id[:8]}"):
            q_oc = st.select_slider(
                "Seberapa menyadari kamu potensi **overconfidence** (terlalu sering trading) "
                "dalam keputusanmu selama sesi ini?",
                options=[1, 2, 3, 4, 5],
                value=3,
                format_func=lambda x: LIKERT[x],
            )
            q_dei = st.select_slider(
                "Seberapa menyadari kamu potensi **efek disposisi** (menjual saham untung "
                "terlalu cepat / menahan saham rugi) dalam sesi ini?",
                options=[1, 2, 3, 4, 5],
                value=3,
                format_func=lambda x: LIKERT[x],
            )
            q_lai = st.select_slider(
                "Seberapa menyadari kamu kecenderungan **loss aversion** (enggan melepas "
                "posisi merugi) yang mungkin memengaruhi keputusanmu?",
                options=[1, 2, 3, 4, 5],
                value=3,
                format_func=lambda x: LIKERT[x],
            )
            q_use = st.select_slider(
                "Seberapa berguna umpan balik yang kamu terima dari sistem ini?",
                options=[1, 2, 3, 4, 5],
                value=3,
                format_func=lambda x: USEFULNESS[x],
            )

            submitted = st.form_submit_button(
                "Kirim Evaluasi Diri", use_container_width=True, type="primary"
            )

        if submitted:
            try:
                with get_session() as save_sess:
                    save_sess.add(PostSessionSurvey(
                        user_id=user_id,
                        session_id=session_id,
                        self_overconfidence=q_oc,
                        self_disposition=q_dei,
                        self_loss_aversion=q_lai,
                        feedback_usefulness=q_use,
                    ))
                st.success(
                    "Terima kasih atas evaluasimu! Data ini sangat membantu penelitian. 🙏"
                )
                st.rerun()
            except Exception:
                import logging as _log
                _log.getLogger(__name__).warning(
                    "Failed to save PostSessionSurvey for user=%d session=%s",
                    user_id, session_id,
                )
                st.warning("Gagal menyimpan survei. Silakan coba lagi.")
```

**Add import** at the top of `modules/feedback/renderer.py`:
```python
from database.connection import get_session
```

`get_session` is already imported — verify this at the top of the file before adding.

---

## TASK G — Tests for V5 features

Create `/sessions/adoring-ecstatic-ptolemy/mnt/TA-18222007/tests/test_v5_features.py`:

```python
"""
tests/test_v5_features.py — Tests for V5 features:
  - Cross-bias interaction scores (N-01)
  - Isolation Forest ML validation (N-02)
  - Post-session survey model (N-03)
"""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base, BiasMetric, User, PostSessionSurvey
from modules.cdt.interaction import compute_interaction_scores, _pearson


# ---------------------------------------------------------------------------
# Shared fixture
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
    u = User(alias="v5_test_user", experience_level="beginner")
    db.add(u)
    db.flush()
    return u


def _add_metric(db, user_id, ocs, dei, lai):
    m = BiasMetric(
        user_id=user_id,
        session_id=str(uuid.uuid4()),
        overconfidence_score=ocs,
        disposition_pgr=max(dei, 0.0),
        disposition_plr=0.0,
        disposition_dei=dei,
        loss_aversion_index=lai,
    )
    db.add(m)
    db.flush()
    return m


# ---------------------------------------------------------------------------
# N-01: Cross-bias interaction scores
# ---------------------------------------------------------------------------

class TestPearsonHelper:
    def test_perfect_positive_correlation(self):
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [2.0, 4.0, 6.0, 8.0, 10.0]
        r = _pearson(xs, ys)
        assert r == pytest.approx(1.0)

    def test_perfect_negative_correlation(self):
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [5.0, 4.0, 3.0, 2.0, 1.0]
        r = _pearson(xs, ys)
        assert r == pytest.approx(-1.0)

    def test_zero_variance_returns_none(self):
        xs = [1.0, 1.0, 1.0]
        ys = [1.0, 2.0, 3.0]
        assert _pearson(xs, ys) is None

    def test_single_element_returns_none(self):
        assert _pearson([1.0], [1.0]) is None


class TestComputeInteractionScores:
    def test_returns_none_below_min_sessions(self, db, user):
        for _ in range(2):
            _add_metric(db, user.id, ocs=0.5, dei=0.3, lai=1.5)
        result = compute_interaction_scores(db, user.id)
        assert result is None

    def test_returns_dict_with_three_sessions(self, db, user):
        for i in range(3):
            _add_metric(db, user.id, ocs=0.3 * (i + 1), dei=0.1 * i, lai=1.0)
        result = compute_interaction_scores(db, user.id)
        assert result is not None
        assert set(result.keys()) == {"ocs_dei", "ocs_lai", "dei_lai"}

    def test_correlated_ocs_lai_detected(self, db, user):
        """Sessions where OCS and LAI rise together → positive ocs_lai correlation."""
        for v in [0.1, 0.3, 0.5, 0.7, 0.9]:
            _add_metric(db, user.id, ocs=v, dei=0.1, lai=v * 3)
        result = compute_interaction_scores(db, user.id)
        assert result["ocs_lai"] is not None
        assert result["ocs_lai"] > 0.8, (
            f"Expected strong positive ocs_lai correlation, got {result['ocs_lai']:.4f}"
        )

    def test_all_none_when_constant_bias(self, db, user):
        """Zero-variance series → all correlations return None."""
        for _ in range(5):
            _add_metric(db, user.id, ocs=0.5, dei=0.3, lai=1.5)
        result = compute_interaction_scores(db, user.id)
        # All series are constant → all correlations undefined
        assert result is not None  # dict is returned, but values are None
        assert all(v is None for v in result.values())


# ---------------------------------------------------------------------------
# N-02: Isolation Forest (graceful degradation only; full test requires sklearn)
# ---------------------------------------------------------------------------

class TestMLValidator:
    def test_returns_none_below_min_sessions(self, db, user):
        from modules.cdt.ml_validator import compute_anomaly_flags
        for _ in range(3):
            _add_metric(db, user.id, ocs=0.5, dei=0.3, lai=1.5)
        result = compute_anomaly_flags(db, user.id)
        assert result is None

    def test_returns_result_with_five_sessions_if_sklearn_available(self, db, user):
        """If sklearn is installed, returns structured dict with 5 sessions."""
        try:
            import sklearn  # noqa: F401
        except ImportError:
            pytest.skip("scikit-learn not installed")

        from modules.cdt.ml_validator import compute_anomaly_flags
        for i in range(5):
            _add_metric(db, user.id, ocs=0.2 * i, dei=0.1, lai=1.0)
        result = compute_anomaly_flags(db, user.id)
        assert result is not None
        assert result["n_sessions"] == 5
        assert len(result["session_ids"]) == 5
        assert len(result["anomaly_scores"]) == 5
        assert len(result["is_anomaly"]) == 5

    def test_returns_none_gracefully_when_sklearn_missing(self, db, user, monkeypatch):
        """Simulate sklearn ImportError → function returns None without raising."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "sklearn.ensemble":
                raise ImportError("sklearn not available (mocked)")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        from modules.cdt.ml_validator import compute_anomaly_flags
        for i in range(6):
            _add_metric(db, user.id, ocs=0.1 * i, dei=0.0, lai=1.0)

        # Should not raise, should return None
        result = compute_anomaly_flags(db, user.id)
        assert result is None


# ---------------------------------------------------------------------------
# N-03: Post-session survey model
# ---------------------------------------------------------------------------

class TestPostSessionSurvey:
    def test_can_create_survey_record(self, db, user):
        sid = str(uuid.uuid4())
        survey = PostSessionSurvey(
            user_id=user.id,
            session_id=sid,
            self_overconfidence=3,
            self_disposition=4,
            self_loss_aversion=2,
            feedback_usefulness=5,
        )
        db.add(survey)
        db.flush()
        loaded = db.query(PostSessionSurvey).filter_by(user_id=user.id).first()
        assert loaded is not None
        assert loaded.self_overconfidence == 3
        assert loaded.self_disposition == 4
        assert loaded.self_loss_aversion == 2
        assert loaded.feedback_usefulness == 5

    def test_unique_constraint_per_user_session(self, db, user):
        """Cannot submit two surveys for the same user+session."""
        from sqlalchemy.exc import IntegrityError
        sid = str(uuid.uuid4())
        db.add(PostSessionSurvey(
            user_id=user.id, session_id=sid,
            self_overconfidence=3, self_disposition=3,
            self_loss_aversion=3, feedback_usefulness=3,
        ))
        db.flush()
        db.add(PostSessionSurvey(
            user_id=user.id, session_id=sid,
            self_overconfidence=4, self_disposition=4,
            self_loss_aversion=4, feedback_usefulness=4,
        ))
        with pytest.raises(IntegrityError):
            db.flush()

    def test_different_sessions_allowed(self, db, user):
        """Same user can submit surveys for different sessions."""
        for _ in range(3):
            db.add(PostSessionSurvey(
                user_id=user.id, session_id=str(uuid.uuid4()),
                self_overconfidence=3, self_disposition=3,
                self_loss_aversion=3, feedback_usefulness=4,
            ))
        db.flush()
        count = db.query(PostSessionSurvey).filter_by(user_id=user.id).count()
        assert count == 3
```

---

## EXECUTION ORDER

Execute tasks in this order to avoid import errors and DB schema conflicts:

```
TASK F.1 → database/models.py        (add PostSessionSurvey)
TASK D.1 → database/models.py        (add interaction_scores column to CognitiveProfile)
TASK D.2 → create interaction.py     (new module)
TASK E.1 → create ml_validator.py    (new module)
TASK D.3 → modules/cdt/updater.py    (add interaction import + call)
TASK D.4 → app.py                    (update profile_data dict + render interaction scores)
TASK E.2 → app.py                    (add anomaly_data fetch + render panel)
TASK A   → app.py                    (fix login form guard — must be last app.py change)
TASK B   → modules/simulation/ui.py  (add type="category")
TASK C.1 → modules/simulation/ui.py  (auto-redirect in _execute_round)
TASK C.2 → modules/feedback/renderer.py (add _render_post_session_survey + CTAs)
TASK G   → create tests/test_v5_features.py
```

---

## VERIFICATION CHECKLIST

After all tasks are complete, run:

```bash
pytest tests/ -v --tb=short
```

Expected: all existing tests pass + new test_v5_features.py passes.

Manual verification:
1. **Auth fix**: Log in → Beranda shows dashboard only, no login form below.
2. **Chart fix**: On simulation page, select any stock → candlestick has no weekend gaps.
3. **Flow fix**: Complete round 14 → spinner → automatically lands on Hasil Analisis page.
4. **Hasil Analisis**: Shows "Mulai Sesi Baru" and "Lihat Profil Kognitif" buttons at bottom.
5. **Hasil Analisis**: Shows post-session survey expander; can submit once; "already submitted" msg on revisit.
6. **Profil page (3+ sessions)**: Shows interaction scores section with Pearson r values.
7. **Profil page (5+ sessions)**: Shows ML anomaly detection panel with per-session table.

---

## CONSTRAINTS (unchanged from V4)

- All UI text and user-facing strings in Bahasa Indonesia.
- Do NOT change bias formulas (DEI, OCS, LAI), EMA parameters, or severity thresholds.
- Do NOT use `datetime.utcnow()` — always `datetime.now(timezone.utc)`.
- Do NOT use `print()` in production code — use `logging.getLogger(__name__)`.
- Do NOT alter conftest.py or any existing V4 test assertions.
- Do NOT restructure folder layout or rename existing modules.
- Tech stack is frozen: Streamlit, SQLAlchemy, pandas, Plotly, pytest.
