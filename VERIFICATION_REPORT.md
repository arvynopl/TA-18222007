# CDT Implementation Verification Report

**Generated:** 2026-04-20  
**Project:** TA-18222007 — Cognitive Digital Twin for Retail Investor Behavioral Bias Detection  
**Pass type:** Read-only verification (no code modified)

---

## Task 1: Entity Count Verification

**Command:** `grep -n "class.*Base" database/models.py`

**Output:**
```
20: class Base(DeclarativeBase):       ← base class declaration (not an entity)
25: class User(Base):
54: class StockCatalog(Base):
74: class MarketSnapshot(Base):
111: class UserAction(Base):
147: class BiasMetric(Base):
181: class CognitiveProfile(Base):
216: class FeedbackHistory(Base):
243: class ConsentLog(Base):
263: class UserSurvey(Base):
293: class SessionSummary(Base):
317: class CdtSnapshot(Base):
357: class PostSessionSurvey(Base):
```

**Actual entity count:** 12 (excluding `Base` itself)

**Entity names:**
1. `User`
2. `StockCatalog`
3. `MarketSnapshot`
4. `UserAction`
5. `BiasMetric`
6. `CognitiveProfile`
7. `FeedbackHistory`
8. `ConsentLog`
9. `UserSurvey`
10. `SessionSummary`
11. `CdtSnapshot`
12. `PostSessionSurvey`

**Result:** ✅ Matches expected count of 12.

---

## Task 2: Stability Formula Verification

**File:** `modules/cdt/stability.py`  
**Function:** `compute_stability_index()` (lines 191–241)

**Exact relevant lines (verbatim):**

```python
    def _std(vals: list[float]) -> float:
        n = len(vals)
        if n < 2:
            return 0.0
        mu = sum(vals) / n
        variance = sum((v - mu) ** 2 for v in vals) / (n - 1)
        return math.sqrt(variance)

    mean_std = (_std(ocs_vals) + _std(dei_vals) + _std(lai_vals)) / 3.0
    return max(0.0, min(1.0, 1.0 - mean_std))
```

**Formula as implemented:** `stability = 1 − mean(std_ocs, std_dei_norm, std_lai_norm)`, clamped to [0, 1].

**⚠ DISCREPANCY — Formula does not match documented CV formula:**

- **Documented (expected):** `1.0 - std(values) / max(mean(values), 0.01)` — a Coefficient of Variation (CV) formula that normalises standard deviation by the mean.
- **Implemented:** `1.0 - mean_std` where `mean_std` is the arithmetic mean of the per-dimension standard deviations. There is **no division by a mean value** anywhere in the function.

The implementation is a simpler "mean of standard deviations" approach, not a CV. Under the CV formula the denominator (`max(mean, 0.01)`) would suppress large standard deviations when the mean is large; the implemented formula has no such suppression. The docstring inside the function correctly describes the implementation (`stability = 1 − mean(std_ocs, std_dei, std_lai)`), so the discrepancy is between the task specification and the code, not between the docstring and the code.

---

## Task 3: Trajectory Function Call Chain Verification

### a) `_classify_bias_trajectory()` — definition and callers

- **Defined at:** `modules/feedback/generator.py:215`
- **Direct caller:** `_get_cdt_modifier()` at `modules/feedback/generator.py:312`
- **Transitive caller:** `generate_feedback()` at `modules/feedback/generator.py:618` calls `_get_cdt_modifier()`

Full chain:
```
generate_feedback()          [generator.py:618]
  └─ _get_cdt_modifier()     [generator.py:312]
       └─ _classify_bias_trajectory()  [generator.py:215]
```

No other production caller exists.

### b) `compute_learning_trajectory()` — definition and callers

- **Defined at:** `modules/cdt/stability.py:84`
- **Production callers:** **None.** A search across all `.py` files outside the test suite found zero imports or calls to `compute_learning_trajectory` in any production module (`updater.py`, `app.py`, any `modules/` subpackage).
- **Test-only callers:** `tests/test_cdt_updater.py` (lines 452, 472, 484, 502).

### c) Two-tier design confirmation

The heuristic trajectory (`_classify_bias_trajectory`) feeds feedback text as intended — confirmed via call chain in (a).

**⚠ DISCREPANCY — Regression trajectory is not wired into the CDT profile view:**

The documented design states "regression trajectory feeds CDT profile view." However:
- `compute_learning_trajectory()` is not called from `update_profile()` (`modules/cdt/updater.py`) or from `app.py`.
- `CognitiveProfile` has no `learning_trajectory` column (confirmed: `grep "learning_trajectory" database/models.py` returns nothing).
- `update_profile()` calls `compute_stability_index()` and `compute_interaction_scores()` but does NOT call `compute_learning_trajectory()`.

The function is implemented and tested but is not integrated into any production flow.

### d) `compute_learning_trajectory()` — UI rendering output

Confirmed: `compute_learning_trajectory()` produces no UI rendering output. It is not called by any route handler or template-rendering function in `app.py`, and returns a `LearningTrajectory` dataclass that is not stored in `CognitiveProfile` or any other persisted model in the current production code.

**Note (per task specification):** The expectation that the result is "stored in CognitiveProfile, not directly rendered per-session" is not met in the current implementation — neither storage nor rendering occurs in production code.

---

## Task 4: Test Suite

**Command:** `pytest tests/ -v --tb=short`

**Result:** ✅ **198 passed, 1 skipped, 0 failed** (runtime: 9.37 s)

The 1 skipped test is `tests/test_v5_features.py::TestMLValidator::test_returns_result_with_five_sessions_if_sklearn_available` — skipped due to optional sklearn dependency.

Exceeds the documented expectation of 85+ passed.

---

## Task 5: `render_interaction_synthesis` Test Coverage

**Command:** `pytest tests/test_renderer.py -v | grep -A2 "TestRenderInteractionSynthesis"`

**Result:** ⚠ **`TestRenderInteractionSynthesis` class does not exist in `tests/test_renderer.py`.**

The grep returned no output. The full test file contains 15 tests across these classes/functions:

| Class / Function | Tests | Status |
|---|---|---|
| `TestSeverityDelta` | 7 methods | All PASSED |
| `TestRenderBiasCard` | 4 methods | All PASSED |
| `test_severity_display_maps_complete` | 1 (standalone) | PASSED |
| `test_bias_display_name_map_complete` | 1 (standalone) | PASSED |
| `TestRenderLongitudinalSection` | 2 methods | All PASSED |

**Total: 15 passed, 0 failed.**

There is no `TestRenderInteractionSynthesis` class with 9 test methods as expected. The interaction synthesis rendering may not yet have a dedicated test class, or the class may have been renamed/relocated.

---

## Discrepancies Summary

| # | Location | Expected | Actual |
|---|---|---|---|
| D1 | `modules/cdt/stability.py:compute_stability_index()` | CV formula: `1.0 - std(values) / max(mean(values), 0.01)` | Different formula: `1.0 - mean(std_ocs, std_dei_norm, std_lai_norm)` — no division by mean |
| D2 | `compute_learning_trajectory()` callers | Called by CDT profile update; result stored in `CognitiveProfile` | No production caller; `CognitiveProfile` has no `learning_trajectory` field; function is test-only |
| D3 | Two-tier trajectory design | Regression trajectory feeds CDT profile view | Regression trajectory (`compute_learning_trajectory`) is not wired to any profile update or UI route |
| D4 | `tests/test_renderer.py` | `TestRenderInteractionSynthesis` class with 9 test methods | Class does not exist; file has 15 tests across different classes |
