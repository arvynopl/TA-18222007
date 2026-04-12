# CDT AI Model & Cognitive Mechanisms — Deep Assessment V2

**Assessor:** Opus 4.6 (Techno-Strategic Architect)
**Date:** 2026-04-09
**Scope:** AI/ML model architecture, CDT state mechanisms, bias detection accuracy, thesis-proposal alignment
**Baseline:** 125/125 tests passing, V1 critical bugs resolved (OCS sigmoid fixed)

---

## 0. EXECUTIVE VERDICT

**The codebase is MVP-sufficient for thesis defense — but the CDT model is architecturally thin relative to what your proposal commits to.**

Current maturity: **~85%** (up from V1's ~75%, reflecting OCS fix, survey priors, insufficient-data guards, and expanded tests). The remaining 15% is concentrated in three areas: (A) the proposal-vs-implementation gap on "ML/machine learning" language, (B) CDT model depth (4-layer architecture described in proposal vs 2-layer implementation), and (C) absence of a quantitative validation framework for FR02's "75% accuracy" claim.

None of these are codebase bugs — they are architectural and methodological gaps that affect your thesis narrative more than your running software.

---

## 1. THE ML/AI LANGUAGE GAP — THE SINGLE BIGGEST THESIS RISK

### What the Proposal Says

Your proposal uses "machine learning" and "AI model" language in at least four critical locations:

| Location | Exact Language | Implied Capability |
|----------|---------------|-------------------|
| IV.1.1.3 (Analytics Module) | "...pendeteksian kecenderungan bias **menggunakan algoritma pembelajaran mesin**" | ML algorithm for bias detection |
| IV.1.4.1.3 (Technology Architecture) | "**ML Processing dan Model Serving Environment**" | A served ML model |
| IV.1.4.2.4 (CDT Model Layer 1) | "Bias Aggregation Layer... **melalui proses inferensi model machine learning**" | ML inference pipeline |
| UC-03 (Use Case) | "Sistem mendeteksi bias **melalui model ML**" | ML model in the detection path |

### What the Implementation Does

The implementation uses **deterministic, closed-form formulas** throughout:

- **DEI** = PGR − PLR (count-based ratio, Odean 1998)
- **OCS** = 2×(sigmoid(freq/perf) − 0.5) (parametric transform)
- **LAI** = avg_hold_losers / max(avg_hold_winners, 1) (ratio)
- **EMA** = α×metric(t) + (1−α)×state(t−1) (exponential smoothing)
- **Severity** = threshold-based classifier (if/else cascade)
- **Feedback** = template slot-filling (string interpolation)

There is **zero learned behavior** anywhere in the pipeline. No training data, no model weights, no gradient descent, no inference step.

### Assessment: Is This a Problem?

**Yes — but it is a framing problem, not a technical one.** The formulas you use are well-grounded in behavioral finance literature. They are arguably *better* for a thesis than a black-box ML model because they are transparent, interpretable, and directly traceable to Odean (1998), Barber & Odean (2000), and Kahneman & Tversky (1979). An ML model trained on your ~15-user UAT dataset would be statistically meaningless anyway (n < 30 sessions per user).

### Recommended Resolution

You have **three options**, presented as a trade-off matrix:

| Option | Thesis Alignment | Implementation Effort | Statistical Validity | Recommendation |
|--------|-----------------|----------------------|---------------------|----------------|
| **A. Reframe the narrative** | Requires proposal errata/clarification in Bab VI | Zero code changes | High — honest about deterministic approach | **RECOMMENDED** |
| **B. Add a lightweight ML validation layer** | Fulfills "ML" language literally | 2-3 days of work | Medium — small n makes ML fragile | ACCEPTABLE |
| **C. Replace formulas with trained ML models** | Fully fulfills proposal | 2-4 weeks | Low — insufficient training data for UAT scale | NOT RECOMMENDED |

**Why Option A is best:**

1. Your formulas ARE computational models — they are parameterized mathematical functions applied to behavioral data. The CDT's EMA update IS a recursive state estimation model (a special case of the Kalman filter family). Framing these as "computational behavioral models" or "algorithmic bias detection" is accurate.
2. Your thesis methodology is DSRM (Design Science Research), which evaluates artifacts by whether they solve the stated problem — not by whether they use a specific technology. The artifact works; that is what matters.
3. Adding ML to satisfy proposal language while having n=50 total sessions would actually *weaken* your thesis by introducing unjustifiable statistical claims.
4. In your Bab VI (Evaluation), you can explicitly address this as a "design decision refinement" from proposal to implementation, citing the sample-size constraint and interpretability advantage as rationale.

**If you choose Option B (lightweight ML validation layer):**

The cleanest approach would be an **anomaly detection cross-check** — train an Isolation Forest or One-Class SVM on the user's session feature vectors (after accumulating ≥5 sessions), and flag sessions where the ML model's anomaly score diverges significantly from the deterministic bias scores. This adds genuine ML inference without replacing the core formulas, and can be framed as "model-assisted validation" in your thesis.

This would require: a new `modules/cdt/ml_validator.py` module, ~100 lines of scikit-learn code, integration into the post-session pipeline, and 3-5 new tests. It would NOT change the bias formulas or feedback generation — it would add a secondary signal.

---

## 2. CDT MODEL DEPTH — 4-LAYER PROPOSAL vs 2-LAYER IMPLEMENTATION

### Proposal's CDT Architecture (Bab IV.2.4)

Your proposal describes a 4-layer CDT model:

| Layer | Proposal Description | Status |
|-------|---------------------|--------|
| **Layer 1: Bias Aggregation** | Aggregate raw metrics into composite bias signal via ML inference | ⚠️ Partially implemented (formulas exist, no ML) |
| **Layer 2: Cognitive State Representation** | bias_intensity_vector + risk_preference + stability_index | ✅ Fully implemented in CognitiveProfile |
| **Layer 3: Update Mechanism** | EMA-based temporal evolution with survey priors | ✅ Fully implemented in updater.py + profile.py |
| **Layer 4: State Persistence** | Database storage with version history | ⚠️ Partially implemented (current state only, no version history) |

### Gap Analysis

**Layer 1 gap:** The "aggregation" is a direct pass-through — OCS goes to overconfidence, |DEI| goes to disposition, min(LAI/3,1) goes to loss_aversion. There is no cross-bias interaction modeling. The proposal implies a richer aggregation that considers how biases interact (e.g., overconfidence amplifying disposition effect, loss aversion dampening risk-taking).

**Layer 4 gap:** CognitiveProfile stores only the *current* state. There is no version history — you can reconstruct past states from BiasMetric rows + EMA replay, but there is no explicit CDT state snapshot per session. This matters for your thesis analysis because you want to show "how the CDT evolved over sessions" in Bab VI.

### Recommended Fixes

**For Layer 1 — Cross-Bias Interaction Coefficient (MEDIUM priority, ~2 hours):**

Add a `bias_interaction_score` to the CognitiveProfile that captures whether biases co-occur. The simplest defensible approach: compute the **pairwise Pearson correlation** of (OCS, |DEI|, LAI_normalized) across the user's session history. If all three biases spike together, the interaction score is high, suggesting a systemic behavioral pattern rather than isolated biases.

This is NOT ML — it is descriptive statistics — but it enriches Layer 1 from "pass-through" to "aggregation with interaction awareness." Implementation: add a `compute_bias_interaction()` function in `stability.py`, store result as a new `bias_interaction_score` field on CognitiveProfile.

**For Layer 4 — CDT State Snapshots (HIGH priority for thesis, ~1 hour):**

Add a `CdtSnapshot` model (or a JSON field on SessionSummary) that captures the full CognitiveProfile state at the end of each session. This gives you a clean time series for Bab VI charts: "CDT evolution over 5 sessions" with exact values at each step.

Without this, you'd need to replay all BiasMetric rows through the EMA formula to reconstruct historical states — doable but fragile and not how a "State Persistence Layer" should work.

---

## 3. BIAS FORMULA CORRECTNESS & EDGE CASES

### 3.1 Disposition Effect (DEI) — CORRECT, with one subtle issue

The formula is textbook Odean (1998): PGR − PLR using count-based ratios. The implementation correctly handles:
- No trades → (0, 0, 0)
- Only winners sold → PGR > 0, PLR = 0 → DEI > 0 ✓
- Break-even trades → excluded from both numerator and denominator ✓
- Open positions valued at final market price (Bug 1 fix from V1) ✓

**Subtle issue: DEI sensitivity to small denominators.**
With 1 realized gain and 0 paper gains, PGR = 1/1 = 1.0. With 0 realized losses and 1 paper loss, PLR = 0/1 = 0.0. DEI = 1.0 → classified "severe." This is technically correct per Odean but may be misleading for a single-trade session. The insufficient-data guard in `generate_feedback()` partially addresses this, but only when `has_trades` is False (zero activity). A single buy+sell in 14 rounds still triggers full severity classification.

**Recommendation:** Add a `min_trades_for_dei` threshold (e.g., ≥3 realized trades required for DEI to be classified above "mild"). This is a **methodological refinement**, not a formula change. Cite Weber & Camerer (1998) or Dhar & Zhu (2006) for requiring minimum sample sizes in PGR/PLR calculations.

| Alternative | Pros | Cons | Verdict |
|------------|------|------|---------|
| min_trades threshold | Prevents single-trade severity inflation | Arbitrary cutoff choice | **Best for thesis** |
| Bayesian smoothing on PGR/PLR | Statistically principled | Complex, harder to explain | Overkill for MVP |
| Leave as-is | No code changes | Single-trade "severe" DEI is misleading | Acceptable but weak |

### 3.2 Overconfidence (OCS) — CORRECT after V1 fix

The shifted sigmoid `2×(sigmoid(raw)−0.5)` is now clean:
- Zero trades → OCS = 0.0 → "none" ✓
- Single buy → OCS ≈ 0.036 → "none" ✓
- Heavy overtrading → OCS → 1.0 asymptotically ✓
- Catastrophic loss (perf_ratio → 0) → clamped via max(perf, 0.01) ✓

**No issues found.** The calibration comments in the docstring are accurate. The threshold boundaries (0.2/0.4/0.7) produce sensible severity classifications for a 14-round session.

### 3.3 Loss Aversion Index (LAI) — CORRECT, with interpretability caveat

The formula `avg_hold_losers / max(avg_hold_winners, 1)` is sound:
- Equal holding periods → LAI ≈ 1.0 → "none" (below 1.2 mild threshold) ✓
- 3× longer losers → LAI ≈ 3.0 → "severe" ✓
- Only winners → LAI = 0.0 ✓

**Interpretability caveat:** LAI = 0.0 has two meanings — "no loss aversion signal" (good) or "insufficient data" (ambiguous). The docstring documents this clearly, and the feedback generator handles it via the `has_trades` guard. However, a user who buys once and sells at a loss (1 loser, 0 winners) gets LAI = hold_period / 1 = hold_period, which for a round-1-buy/round-14-sell = 13.0 → extreme "severe." This is mathematically correct but behaviorally meaningless with n=1.

**Recommendation:** Same as DEI — add `min_trades_for_lai` requiring ≥2 realized trades (at least 1 winner and 1 loser) for LAI severity above "mild."

---

## 4. EMA UPDATE MECHANISM — SOLID, with enhancement opportunities

### Current Implementation Review

```python
new_oc   = 0.3 × OCS          + 0.7 × old_overconfidence
new_disp = 0.3 × |DEI|        + 0.7 × old_disposition
new_la   = 0.3 × min(LAI/3,1) + 0.7 × old_loss_aversion
new_risk = 0.2 × observed_risk + 0.8 × old_risk_pref  # BETA=0.2, so (1−BETA)=0.8
```

**Correctness:** Sound. EMA is an appropriate choice for longitudinal profiling because:
1. It requires no stored history (constant memory) — only current state + new observation
2. It naturally decays old observations exponentially
3. Survey priors integrate cleanly as initial conditions
4. It converges provably: after n sessions, error ≤ TARGET × (1−α)^n

**Test coverage:** Excellent. `test_ema_convergence_after_many_sessions` (10 sessions at OCS=0.8 → within 0.15 of target) and `test_survey_prior_convergence` (3 zero-bias sessions → prior decays below 35%) are strong convergence guards.

### Enhancement Opportunities

**Enhancement 1: Adaptive α Based on Session Quality (MEDIUM priority)**

Currently α=0.3 is fixed. A session where the user made 2 trades and held everything else should weight less than a session with 12 active trades. The observation is noisier when the user is less active.

**Proposed formula:**
```
session_activity = (buy_count + sell_count) / (2 × ROUNDS_PER_SESSION)  # normalized [0,1]
effective_alpha = ALPHA_MIN + (ALPHA_MAX - ALPHA_MIN) × session_activity
# Where ALPHA_MIN=0.1, ALPHA_MAX=0.4
```

This means high-activity sessions update the CDT more aggressively, while low-activity sessions (which produce noisier metrics) update it more conservatively.

| Alternative | Pros | Cons | Verdict |
|------------|------|------|---------|
| Adaptive α (activity-weighted) | Reduces noise from low-activity sessions | Adds 2 config params | **Best for thesis quality** |
| Confidence-weighted EMA | Statistically elegant | Complex to calibrate | Overkill |
| Fixed α (current) | Simple, well-tested | Treats all sessions equally regardless of signal quality | Acceptable |

**Enhancement 2: LAI Normalization Ceiling (LOW priority)**

LAI is normalized as `min(LAI/3, 1.0)` before EMA. The divisor 3.0 is hardcoded and undocumented. It means LAI≥3.0 saturates the EMA input at 1.0. This is reasonable (LAI=3 is extreme loss aversion) but should be a named constant in config.py (e.g., `LAI_EMA_CEILING = 3.0`) with a docstring explaining the choice.

---

## 5. STABILITY INDEX — FUNCTIONAL but IMPROVABLE

### Current Implementation

```python
stability = 1 − mean(std(OCS), std(DEI), std(LAI_norm))  # clamped [0,1]
```

Uses sample standard deviation across last 5 sessions. Returns 0.0 for <2 sessions.

### Issues

**Issue 1: Unweighted mean of stds with different scales.**
OCS ∈ [0,1), DEI ∈ [-1,1] (but stored as raw DEI, not |DEI|, in BiasMetric), LAI_norm ∈ [0,1]. The raw DEI can swing from -0.8 to +0.8, giving std ≈ 0.8, while OCS typically varies within [0.1, 0.5], giving std ≈ 0.15. The stability index is therefore dominated by whichever bias has the widest range, not the most inconsistent pattern.

**Issue 2: Uses signed DEI for stability.**
The code comment says "Use raw (signed) DEI so oscillation between positive and negative values registers as high variance." This is a defensible design choice — but it means a user who consistently shows DEI=+0.3 every session (stable moderate disposition) will have lower std than a user who alternates DEI=+0.1 and DEI=-0.1 (actually less biased but classified as "unstable").

**Recommendation:** Normalize each dimension to [0,1] **before** computing std. OCS is already in [0,1). For DEI, use |DEI| (which is what the EMA uses). LAI is already normalized. This makes the stability index measure consistency of bias *intensity* rather than consistency of raw metric values.

| Alternative | Pros | Cons | Verdict |
|------------|------|------|---------|
| Normalize then std (recommended) | Dimensions weighted equally | Slightly changes semantics | **Best** |
| Coefficient of variation (CV) | Scale-invariant | Undefined when mean=0 | Fragile |
| Current (raw std) | Already tested | DEI dominates | Acceptable |

---

## 6. SURVEY PRIORS — WELL-DESIGNED

The survey prior system is one of the strongest parts of the CDT implementation:

- Likert 1-5 → normalized [0,1] → damped by SURVEY_PRIOR_WEIGHT=0.15
- Maximum possible prior = 0.15 (below OCS_MILD=0.20) — verified by `test_extreme_survey_below_mild_threshold`
- Priors decay naturally under EMA: after 3 zero-bias sessions, prior < 0.35 × initial — verified by `test_survey_prior_convergence`
- Users without surveys start at {0,0,0} — clean baseline

**No changes needed.** This is well-engineered and well-tested.

---

## 7. COUNTERFACTUAL ANALYSIS — NEEDS FIX

### Current Implementation

```python
trend_per_round = (sell_price - buy_price) / max(sell_round - buy_round, 1)
projected_price = sell_price + trend_per_round * extra_rounds
```

This is **linear extrapolation** from the buy→sell price trend. It has two problems:

1. **Can project negative prices** for stocks that were sold at a loss (trend_per_round < 0, projected_price < sell_price)
2. **Ignores actual market data** — the simulation has real MarketSnapshot prices for future rounds. The counterfactual should use them.

### Recommended Fix

Replace the linear extrapolation with actual market data lookup. The simulation window is 14 rounds; if the user sold at round 10, rounds 11-14 have actual snapshot prices in the database. This is a **fundamental** fix — linear extrapolation is not a valid counterfactual methodology.

```python
# Pseudocode for the fix:
target_round = sell_round + extra_rounds
target_snapshot = query MarketSnapshot for stock_id at window_start_date + target_round days
if target_snapshot:
    projected_price = target_snapshot.close
    projected_gain = (projected_price - buy_price) * quantity
```

This requires passing the simulation window's start date into `compute_counterfactual()`, which is available from SessionSummary (if populated) or derivable from the action timestamps.

| Alternative | Pros | Cons | Verdict |
|------------|------|------|---------|
| Actual market data (recommended) | Factually correct counterfactual | Requires window_start_date parameter | **Best — fundamental fix** |
| Linear extrapolation with floor(0) | Prevents negative prices | Still misleading | Band-aid |
| Remove counterfactual entirely | Simplest | Loses a valuable educational feature | Waste |

---

## 8. FEEDBACK PERSONALIZATION — ADEQUATE but STATIC

### Current State

Feedback is generated from 9 template pairs (3 biases × 3 severities) with slot interpolation. Templates are well-written in Bahasa Indonesia, include academic citations (Barber & Odean, Kahneman & Tversky), and provide actionable recommendations.

### What's Missing

The CDT profile (bias_intensity_vector, stability_index, risk_preference, session_count) is **not used in feedback generation**. The feedback is purely session-local — it looks at the current BiasMetric and ignores the longitudinal profile.

This means:
- A first-time user with OCS=0.45 gets the same "moderate overconfidence" message as a 10-session veteran with OCS=0.45
- A user whose overconfidence is *declining* (CDT trend improving) gets the same warning as one whose overconfidence is *rising*
- The stability_index is computed but never affects feedback tone

### Recommended Enhancement: CDT-Aware Feedback Modifiers

Add a **feedback modifier layer** between severity classification and template rendering. This is NOT a new template system — it appends contextual sentences to existing templates based on CDT state.

```python
# Pseudocode:
modifiers = []
if profile.session_count >= 3:
    if current_severity < previous_severity:
        modifiers.append("Bagus! Skor kamu menunjukkan perbaikan dari sesi sebelumnya.")
    elif current_severity > previous_severity:
        modifiers.append("Perhatian: bias ini meningkat dibanding sesi sebelumnya.")
if profile.stability_index > 0.8 and severity in ("moderate", "severe"):
    modifiers.append("Pola ini konsisten di beberapa sesi — pertimbangkan strategi berbeda.")
```

This is ~50 lines of code, requires no new templates, and dramatically enriches the CDT's "adaptive feedback" capability — which is a core thesis claim.

| Alternative | Pros | Cons | Verdict |
|------------|------|------|---------|
| CDT-aware modifiers (recommended) | Demonstrates longitudinal adaptation | ~50 lines new code | **Best for thesis** |
| Full CDT-conditional templates | Most flexible | 27+ template variants needed | Over-engineered |
| Current (session-local) | Already works | Ignores CDT entirely in feedback | Undersells the system |

---

## 9. VALIDATION FRAMEWORK — THE MISSING PIECE FOR FR02

### The Problem

FR02 in your proposal states: **"Sistem mendeteksi bias perilaku investasi dengan akurasi ≥75%"** (System detects investment behavioral biases with ≥75% accuracy).

There is currently **no mechanism to measure this accuracy**. The system produces bias scores and severity classifications, but there is no ground truth to validate against. This is not a code bug — it is a methodological gap that your thesis defense panel will almost certainly question.

### What "Accuracy" Means for This System

For a bias detection system without labeled ground truth, accuracy must be operationalized differently than ML classification accuracy. The most defensible approaches:

**Approach 1: Expert Benchmark Validation (RECOMMENDED)**

Design a set of 10-15 scripted "synthetic sessions" with known behavioral patterns:
- Session A: Buy all stocks round 1, sell only winners round 7, hold losers → Expected: DEI=severe, OCS=moderate, LAI=moderate
- Session B: Hold all 14 rounds, zero trades → Expected: all none
- Session C: Buy/sell every round regardless of P&L → Expected: OCS=severe, DEI=low, LAI=low

Run these through the pipeline programmatically (like test_integration.py but with richer scenarios). Calculate: `accuracy = sessions_where_all_severities_match_expected / total_sessions`. If ≥75%, FR02 is met.

**This can be done entirely in the test suite** — it does not require UAT users. Add a `tests/test_validation_scenarios.py` file with ~15 benchmark scenarios that map known behavioral patterns to expected severity outcomes.

**Approach 2: Post-UAT Self-Assessment Survey**

After each session, ask the user: "Apakah kamu merasa bahwa kamu: (a) terlalu sering trading, (b) menahan posisi rugi terlalu lama, (c) menjual saham untung terlalu cepat?" Compare their self-assessment to the system's severity classification. This is weaker (self-report bias) but adds a human validation dimension.

**Approach 3: Inter-Session Consistency (already partially implemented)**

If a user shows "severe overconfidence" in session 1 and "none" in session 2 with similar trading behavior, the system is inconsistent. The stability index partially captures this, but a formal consistency metric (e.g., test-retest reliability via Cronbach's alpha across sessions) would strengthen FR02.

| Approach | Rigor | Effort | Thesis Value | Verdict |
|----------|-------|--------|-------------|---------|
| Synthetic benchmark scenarios | High | 1 day | Directly addresses FR02 | **RECOMMENDED** |
| Post-UAT self-assessment | Medium | 2 hours (UI) | Adds human validation | Good complement |
| Consistency metric | Medium | 2 hours | Shows reliability | Good complement |

---

## 10. TESTING QUALITY — STRONG, with specific gaps

### Current State: 125/125 tests passing

| Test File | Count | Coverage Area |
|-----------|-------|--------------|
| test_bias_metrics.py | 26 | All three formulas + severity classifier |
| test_cdt_updater.py | 13 | Profile CRUD, EMA convergence, stability, survey priors |
| test_integration.py | 5 | End-to-end pipeline, 3-session convergence, 12-stock |
| test_feedback.py | 12 | Templates, generation, longitudinal summary |
| test_simulation.py | 17 | Portfolio buy/sell/hold mechanics |
| test_features.py | 5 | Feature extraction |
| test_counterfactual.py | 4 | Counterfactual edge cases |
| test_export.py | 6 | CSV export utilities |
| test_validator.py | 5 | Session completeness |
| test_survey.py | 7 | UserSurvey model + export |
| test_free_choice.py | 10 | Partial stock coverage, auto-hold |
| test_renderer.py | 8 | Feedback rendering |
| test_portfolio_extended.py | 7 | Additional portfolio scenarios |

### Identified Gaps

1. **No boundary tests for EMA with survey priors + live data.** Tests verify priors alone and EMA alone, but not: "User with survey prior of 0.15 gets 5 sessions with OCS=0.8 — does the CDT converge correctly past the prior?"

2. **No adversarial/stress tests.** What happens with: extreme values (LAI=100, OCS at sigmoid overflow), NaN/None in BiasMetric fields, concurrent sessions for the same user, >100 sessions for one user?

3. **No FR02 validation scenarios** (covered in Section 9).

4. **Counterfactual tests don't cover the linear extrapolation producing negative prices.** `test_counterfactual.py` has 4 tests but none for a losing trade where the trend_per_round is negative and extra_rounds push projected_price below zero.

---

## 11. PRIORITIZED RECOMMENDATION MATRIX

### Must-Have for Thesis Defense (before UAT)

| # | Item | Type | Effort | Impact |
|---|------|------|--------|--------|
| R-01 | Reframe ML language in thesis text (Bab VI) | Narrative | 0 code | Eliminates biggest defense risk |
| R-02 | Add FR02 validation scenarios (`test_validation_scenarios.py`) | Testing | 4 hours | Directly addresses FR02 "75% accuracy" |
| R-03 | Fix counterfactual to use actual market data | Fundamental | 2 hours | Corrects methodologically unsound approach |
| R-04 | Add CDT state snapshots per session | Architecture | 1 hour | Enables Bab VI longitudinal analysis |
| R-05 | CDT-aware feedback modifiers | Feature | 2 hours | Demonstrates adaptive feedback claim |

### Should-Have for Thesis Quality

| # | Item | Type | Effort | Impact |
|---|------|------|--------|--------|
| R-06 | min_trades threshold for DEI/LAI severity | Methodological | 1 hour | Prevents single-trade severity inflation |
| R-07 | Normalize stability index dimensions | Technical | 30 min | Removes DEI dominance in stability calc |
| R-08 | Move LAI/3 ceiling to config constant | Code quality | 15 min | Makes normalization explicit and tunable |
| R-09 | Adaptive α based on session activity | Enhancement | 1 hour | Reduces noise from low-activity sessions |
| R-10 | Boundary/stress tests for EMA edge cases | Testing | 1 hour | Strengthens test suite for defense |

### Nice-to-Have (if time permits)

| # | Item | Type | Effort | Impact |
|---|------|------|--------|--------|
| R-11 | Cross-bias interaction score | Feature | 2 hours | Enriches Layer 1 aggregation |
| R-12 | Lightweight ML validation (Isolation Forest) | Feature | 3 days | Literally fulfills "ML" language |
| R-13 | Post-UAT self-assessment survey | UI | 2 hours | Adds human validation for FR02 |

---

## 12. WHAT IS NOT BROKEN (DO NOT TOUCH)

1. **Bias formulas (DEI, OCS, LAI)** — correct and well-cited
2. **EMA core logic** — mathematically sound, well-tested
3. **Survey prior integration** — clean, correctly damped, verified
4. **Template system** — well-localized Bahasa Indonesia, academic citations
5. **Portfolio mechanics** — pure Python, no DB dependency, edge-case tested
6. **Feature extraction** — two-pass replay with batch-fetch optimization
7. **Test infrastructure** — in-memory SQLite fixtures, clean separation
8. **ORM schema** — 10 entities with proper cascades and indexes

---

## 13. FRAMING GUIDANCE FOR THESIS DEFENSE

### Q: "Your proposal says ML — where is the machine learning?"

**Suggested response:** "Selama tahap implementasi, kami mengevaluasi trade-off antara pendekatan ML dan formula deterministik. Dengan ukuran sampel UAT (n ≈ 15 pengguna, ≈ 50 sesi), model ML tidak dapat dilatih secara valid — minimum n > 100 sesi per pola bias dibutuhkan untuk generalisasi yang bermakna. Kami memilih formula deterministik yang berakar pada literatur behavioral finance (Odean 1998, Barber & Odean 2000, Kahneman & Tversky 1979) karena transparansi, interpretabilitas, dan validitas statistik. CDT tetap menggunakan model komputasional — EMA adalah kasus khusus dari keluarga estimasi state rekursif (Kalman filter), dan sigmoid OCS adalah model parametrik. Perbedaan ini didokumentasikan sebagai refinement desain di Bab VI."

### Q: "How do you validate the 75% accuracy claim?"

**Suggested response:** "Kami mengoperasionalisasikan akurasi melalui benchmark validation: 15 skenario sintetis dengan pola perilaku yang diketahui (e.g., jual semua winner, tahan semua loser → expected DEI=severe). Sistem mencapai X/15 correct severity classifications = Y%. Selain itu, kami memverifikasi konsistensi longitudinal melalui stability index — pengguna dengan perilaku konsisten menunjukkan stability > 0.7 di seluruh sesi."

---

## 14. CONCLUSION

The CDT codebase is technically sound and MVP-complete. The bias detection formulas are academically grounded, the EMA mechanism is well-tested, and the feedback system works end-to-end. The primary risks are **narrative** (ML language gap), **methodological** (no FR02 validation), and **depth** (CDT-aware feedback not leveraging the profile it computes).

Estimated effort for all Must-Have items (R-01 through R-05): **~9 hours of focused Claude Code work**. This would bring the system to ~95% thesis readiness.

The codebase does not need a fundamental rewrite. It needs targeted enhancements that strengthen the thesis narrative and demonstrate the CDT's adaptive capabilities more convincingly.
