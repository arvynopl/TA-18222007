# CDT Bias Detection System
### Sistem Deteksi dan Mitigasi Bias Perilaku bagi Investor Ritel di Pasar Modal Indonesia

A **Cognitive Digital Twin (CDT)** prototype that detects three behavioral biases — Disposition Effect, Overconfidence, and Loss Aversion — in retail investors through a 14-round historical-replay trading simulation on 12 IDX stocks.

This README is the single source of truth for both local development and Streamlit Community Cloud deployment. It supersedes the previous `README_DEPLOY.md`.

> **Audience-specific entry points:**
> - **Developers** → start at *Quick Start* (next section).
> - **UAT participants** → see [`docs/PANDUAN_PENGUJI_UAT.md`](docs/PANDUAN_PENGUJI_UAT.md) (Bahasa Indonesia).
> - **Researcher (thesis author)** → see [`docs/UAT_RESEARCHER_PLAN.md`](docs/UAT_RESEARCHER_PLAN.md) for the UAT execution playbook.
> - **Thesis advisors deploying for the first time** → jump to *Production Deployment* below.

---

## Quick Start (Local Development)

### Prerequisites
- Python 3.11+
- pip
- Internet connection (for the first-time market-data download)

### One-command setup
```bash
bash setup.sh
```

### Manual setup
```bash
git clone https://github.com/arvynopl/TA-18222007.git
cd TA-18222007
pip install -r requirements.txt
python idx_data_acquisition.py     # downloads OHLCV for 12 IDX tickers
python -m database.seed            # idempotent seed of stock catalog + snapshots
streamlit run app.py
```

The app opens at `http://localhost:8501`.

### Run tests
```bash
pytest tests/ -v
```
Target: **~270 tests passing, 0 failures** across 33 test files.

---

## System Overview

The system implements a 5-stage pipeline repeated across multiple sessions per user:

```
Simulation (14 rounds × 12 IDX stocks, free-choice trading)
    → Action Logging (UserAction — auto-hold for non-traded stocks)
        → Feature Extraction (SessionFeatures dataclass)
            → Bias Metrics (DEI, OCS, LAI + 95% bootstrap CI)
                → CDT Profile Update (EMA + activity-weighted alpha)
                    → Personalized Feedback (template-based, severity-tiered)
                        → Post-session self-assessment survey
```

### Three Detected Biases

| Bias | Formula | Mild | Moderate | Severe |
|---|---|---|---|---|
| **Disposition Effect (DEI)** | PGR − PLR (dollar-weighted, Frazzini 2006; toggleable to Odean 1998 count-based) | > 0.05 | > 0.15 | > 0.50 |
| **Overconfidence (OCS)** | sigmoid(trade_freq / perf_ratio) (Barber & Odean 2000) | > 0.20 | > 0.40 | > 0.70 |
| **Loss Aversion (LAI)** | avg_hold_losers / avg_hold_winners (Kahneman & Tversky 1979) | > 1.20 | > 1.50 | > 2.00 |

A floor rule (`MIN_TRADES_FOR_FULL_SEVERITY = 3`) caps DEI/LAI severity at "mild" for sessions with too few realized round-trips, preventing single-trade artifacts from triggering severe classifications.

### CDT Update (Activity-Weighted Exponential Moving Average)

```
α_effective = ALPHA + (ALPHA_MAX − ALPHA) × activity_ratio       [activity ∈ {0,1}]
BiasIntensity(t) = α_effective × BiasMetric(t) + (1 − α_effective) × BiasIntensity(t−1)
RiskPreference(t) = β × ObservedRisk(t) + (1 − β) × RiskPreference(t−1)        [β = 0.2]
StabilityIndex(t) = 1 − mean(σ_OCS, σ_DEI, σ_LAI) over last CDT_STABILITY_WINDOW (5) sessions
```

Survey-informed priors: if an `OnboardingSurvey` exists, the initial `bias_intensity_vector` is seeded via `compute_survey_priors()` with `SURVEY_PRIOR_WEIGHT = 0.15` damping. Users without an onboarding survey initialize at `{0, 0, 0}`.

### Stock Universe (12 IDX Stocks)

| Ticker | Company | Sector | Volatility |
|---|---|---|---|
| BBCA.JK | Bank Central Asia | Finance | Low |
| TLKM.JK | Telkom Indonesia | Telecom | Low–Medium |
| ANTM.JK | Aneka Tambang | Mining | High |
| GOTO.JK | GoTo Gojek Tokopedia | Technology | High |
| UNVR.JK | Unilever Indonesia | Consumer | Medium |
| BBRI.JK | Bank Rakyat Indonesia | Finance | Medium |
| ASII.JK | Astra International | Conglomerate | Medium |
| BMRI.JK | Bank Mandiri | Finance | Low–Medium |
| ICBP.JK | Indofood CBP Sukses Makmur | Consumer | Low |
| MDKA.JK | Merdeka Copper Gold | Mining | High |
| BRIS.JK | Bank Syariah Indonesia | Finance | Medium |
| EMTK.JK | Elang Mahkota Teknologi | Media & Tech | High |

Only `volatility_class == "high"` stocks contribute to `observed_risk` in the CDT update — a deliberate simplification documented in `config.py`.

---

## Architecture

```
app.py                      Streamlit entry point (5 user pages + hidden researcher view)
config.py                   All thresholds and tunable parameters
database/
  models.py                 14 ORM entities (SQLAlchemy 2.0)
  connection.py             Session factory and DB init
  seed.py                   Stock catalog + market snapshot seeding
modules/
  simulation/               UI, engine (random 14-day window selection), portfolio
  logging_engine/           Action logger (with auto-hold), session validator
  analytics/                Bias metrics, feature extraction, comparison, baselines
  cdt/                      Profile CRUD, EMA updater, stability, snapshot, ML validator
  feedback/                 Template generator + renderer (3 biases × 4 severity levels)
  auth/                     Bcrypt password hashing, rate limiting, registration
  utils/                    Per-user export, cohort export, layout, UI helpers
pages/
  researcher.py             Hidden cohort dashboard (URL-only, password-gated)
tests/                      pytest suite (~270 tests, 33 files)
data/
  stock_catalog.json        12 IDX stock definitions
  all_market_snapshots.csv  ~2826 rows of OHLCV + indicators
docs/
  PANDUAN_PENGUJI_UAT.md    Participant guide (Bahasa Indonesia)
  UAT_RESEARCHER_PLAN.md    Researcher's UAT execution playbook
```

### Database Entities

| Entity | Purpose |
|---|---|
| `User` | Investor identified by `username` (v6) with bcrypt `password_hash`. Legacy `alias` retained. |
| `UserProfile` | One-time demographic snapshot at registration (full name, age, gender, risk profile, experience). |
| `OnboardingSurvey` | 9-item Likert bias-tendency survey (3 items × DEI, OCS, LAI) captured at registration. |
| `UserSurvey` | Legacy 4-item self-report; retained for backward compatibility with comparison engine. |
| `StockCatalog` | 12 IDX stock metadata. |
| `MarketSnapshot` | Daily OHLCV + MA5 / MA20 / RSI / volatility / trend. |
| `UserAction` | Every buy / sell / hold decision per round, with response time. |
| `BiasMetric` | Computed DEI / OCS / LAI per session, with 95% bootstrap CI bounds. |
| `CognitiveProfile` | EMA-updated bias intensity vector + risk preference + stability index (current state). |
| `CdtSnapshot` | Point-in-time CDT state per completed session (longitudinal trajectory). |
| `FeedbackHistory` | Delivered feedback text per (session, bias). |
| `ConsentLog` | UAT participant consent audit trail. |
| `SessionSummary` | Session lifecycle tracking (in_progress / completed / abandoned). |
| `PostSessionSurvey` | Post-feedback metacognition: self-rated bias awareness + feedback usefulness. |
| `UATFeedback` | 10-item SUS responses + open-ended UX feedback. **Append-only**: each submission is a new row; latest is used for analysis. |
| `SessionError` | Lightweight DB-backed error counter (no third-party APM). |

---

## Configuration

### Key parameters (`config.py`)

| Parameter | Default | Description |
|---|---|---|
| `INITIAL_CAPITAL` | Rp 10,000,000 | Starting portfolio value |
| `ROUNDS_PER_SESSION` | 14 | Trading rounds per simulation session |
| `ALPHA` | 0.3 | Base EMA weight for bias intensity |
| `ALPHA_MAX` | 0.45 | Activity-weighted upper bound for EMA |
| `BETA` | 0.2 | EMA weight for risk preference |
| `SURVEY_PRIOR_WEIGHT` | 0.15 | Damping factor for survey-seeded CDT priors |
| `CDT_STABILITY_WINDOW` | 5 | Sessions used for stability index |
| `MIN_TRADES_FOR_FULL_SEVERITY` | 3 | Floor on realized trades before DEI/LAI can exceed mild |
| `USE_DOLLAR_WEIGHTED_DEI` | True | Toggle Frazzini 2006 vs Odean 1998 DEI variant |

### Environment variables

| Variable | Required for | Effect |
|---|---|---|
| `CDT_DATABASE_URL` | Production (mandatory on Streamlit Cloud) | Override default SQLite path; `postgresql://...` for prod |
| `CDT_BCRYPT_ROUNDS` | Optional | Override bcrypt cost factor (default 12) |
| `CDT_RESEARCHER_PASSWORD` | Researcher view | Enables `?view=researcher`; unset → page disabled |
| `CDT_ADMIN_TOKEN` | Admin dashboard | Token for `?admin=<token>` summary view |
| `CDT_DEBUG` | Optional | `=1` enables verbose DEBUG logging to `app.log` |

---

## Researcher Mode (Hidden Cohort Dashboard)

A password-gated cohort-level inspection page is available at:

```
http://localhost:8501/?view=researcher
```

Set `CDT_RESEARCHER_PASSWORD` in the environment (or in Streamlit Cloud Secrets). The page is **read-only** — no DB writes — and provides:

- Cohort summary KPIs (total users, sessions, mean DEI/OCS/LAI, completion rate)
- Per-user table with demographic + onboarding + CDT vectors
- Bias intensity distributions with severity-threshold overlays
- Longitudinal CDT trajectory across sessions, per-user
- Survey-vs-observed validation scatter plots with Pearson r
- ML model performance (when `python scripts/run_ml_validation.py` has been run)
- **UAT survey & post-session survey exports** (full submission history, CSV)
- Bulk CSV download (all users, all sessions, all CDT snapshots)

The route is wired in `app.py:main()` early-return *before* the standard top nav, so UAT participants never see it through normal navigation. The page itself lives at `pages/researcher.py`; cohort helpers live at `modules/utils/research_export.py` (unit-tested in `tests/test_research_export.py`).

When `CDT_RESEARCHER_PASSWORD` is unset, the URL renders an inactive-mode notice and stops. When set, a password form gates access via the `researcher_authed` session flag.

---

## Production Deployment — Streamlit Community Cloud + Neon Postgres

This section walks through the production deploy from GitHub to Streamlit Community Cloud, end-to-end. It is written so a non-developer (e.g. a thesis advisor) can follow it as a checklist.

> **Reading order:** §1 (Neon) → §2 (Streamlit Cloud) → §3 (verification) → §4 (rollback if needed) → §5 (troubleshooting).

### Prerequisites

- A GitHub account with access to `arvynopl/TA-18222007`.
- A web browser (Chrome / Edge / Firefox / Safari).
- 15–30 minutes of uninterrupted time for the first deploy.

You do **not** need a local Python install for production deployment. Everything happens in the browser.

### §1. One-time Neon Postgres setup

The app needs a managed Postgres database because Streamlit Cloud's container filesystem is wiped on every redeploy. Neon's free tier is sufficient for UAT (≥100 testers).

**1.1 Create the Neon project**

1. Go to <https://neon.tech> and sign in with GitHub.
2. Click **New Project**.
3. Fill in:
   - **Project name:** `cdt-bias-uat` (any name is fine).
   - **Postgres version:** keep the default (16+).
   - **Region:** pick the option closest to Indonesia. As of 2026 the nearest is `Asia Pacific (Singapore) — ap-southeast-1`. If that is unavailable, pick `Asia Pacific (Tokyo)` or `US West`.
   - **Database name:** `cdt_bias` (any name is fine, just remember it).
4. Click **Create project**.

*Success check:* you land on the project dashboard with a green "Active" badge.

**1.2 Copy the connection string**

1. On the project dashboard, click **Connection Details** (or the **Dashboard → Connection string** tab).
2. Make sure the **Pooled connection** toggle is **ON** (Streamlit Cloud's serverless containers benefit from the Neon pooler).
3. Click the **copy** icon next to the URL. The string looks like:

   ```
   postgresql://neondb_owner:abc123XYZ@ep-cool-name-12345.ap-southeast-1.aws.neon.tech/cdt_bias?sslmode=require
   ```

4. Paste it into a temporary scratchpad — you will use it in §2.3.

> **Security note:** treat this string like a password. Do not paste it into chat, email, or commit it to git. The repo's `.gitignore` already blocks `.streamlit/secrets.toml`.

**1.3 (Optional) seed the database from your local machine**

This is **optional** because the app calls `run_seed()` on its first boot and the operation is idempotent. If you prefer to pre-seed:

```bash
git clone https://github.com/arvynopl/TA-18222007.git
cd TA-18222007
pip install -r requirements.txt
export CDT_DATABASE_URL='<paste-neon-url-here>'
python -m database.seed
```

*Success check:* the script prints `Seed complete` and exits with code 0.

### §2. Streamlit Community Cloud setup

**2.1 Sign in**

1. Go to <https://streamlit.io/cloud>.
2. Click **Sign in** and authorise with the GitHub account that owns (or has access to) `arvynopl/TA-18222007`.

**2.2 Create the app**

1. Click **Create app** → **Deploy a public app from GitHub**.
2. Fill in:
   - **Repository:** `arvynopl/TA-18222007`
   - **Branch:** `main`
   - **Main file path:** `app.py`
   - **App URL:** pick a subdomain, e.g. `cdt-bias-uat`. The full URL will be `https://cdt-bias-uat.streamlit.app`.
3. **Do not click Deploy yet.** Open **Advanced settings** first.

**2.3 Add the secrets**

In **Advanced settings → Secrets**, paste:

```toml
CDT_DATABASE_URL = "postgresql://<user>:<pass>@<host>.neon.tech/<db>?sslmode=require"
CDT_RESEARCHER_PASSWORD = "<a-strong-password-only-you-know>"
CDT_ADMIN_TOKEN = "<another-random-token>"
```

Replace placeholders with real values. Keep the double quotes. Click **Save**.

> **Why this matters:** the app contains a startup guard (`app.py:_looks_like_streamlit_cloud`). If it detects Streamlit Cloud *and* `CDT_DATABASE_URL` is unset, it refuses to boot — preventing the silent SQLite-data-loss footgun.

**2.4 Confirm Python version**

Streamlit Cloud reads `.python-version` from the repo root and pins to the version listed there (currently `3.11`). No action needed; just confirm the **Python version** dropdown in **Advanced settings** shows `3.11` (or "Auto").

**2.5 Deploy**

Click **Deploy**. The first build takes 3–5 minutes. Watch the live log for errors. You will see:

```
[manager] Installing requirements: streamlit==1.39.0, sqlalchemy==2.0.36, ...
[manager] Your app is in the oven
...
[manager] Your app is live!
```

### §3. First-deploy verification checklist

Open the live URL (e.g. `https://cdt-bias-uat.streamlit.app`) and walk through this list. Tick each box mentally before declaring success.

- [ ] **Page loads.** The hero shows *"Kenali Pola Investasi Anda"* and the *Beranda* navigation tab is highlighted. No red error banner at the top.
- [ ] **No startup guard fired.** If you instead see a red box that says *"Konfigurasi belum lengkap"*, your secret is missing or misnamed. Go back to §2.3.
- [ ] **DB init succeeded.** The first page render runs `run_seed()`. In the Streamlit Cloud log you should see no `OperationalError` or `psycopg2` traceback. The Neon dashboard shows the database size jump from ~0 to ~5 MB once seeded.
- [ ] **Smoke test — register.** Click through the sign-up flow with a throwaway username (e.g. `smoketest1`) and password. Confirm you land on the simulation page.
- [ ] **Smoke test — simulation.** Open *Simulasi Investasi*. Confirm round 1 of 14 renders with a candlestick chart and 12 stocks listed.
- [ ] **Smoke test — persistence.** Refresh the page. Your simulation progress should still be there — proving Postgres (not SQLite) is backing the writes.
- [ ] **Researcher view.** Open `<url>?view=researcher`, log in with `CDT_RESEARCHER_PASSWORD`. Confirm all seven tabs render (Ringkasan / Peserta / Distribusi / Trajektori / Survei vs Observasi / Model ML / Ekspor).
- [ ] **Neon row count.** In the Neon SQL editor run:

      ```sql
      SELECT COUNT(*) FROM users;
      SELECT COUNT(*) FROM market_snapshots;
      ```

      `users` should be ≥ 1 (your smoketest account). `market_snapshots` should be ~2826.
- [ ] **No data in repo.** Run `git status` locally — you should see no new files. The app must never write to the container disk.

If every box is ticked, the deploy is good. Share the URL with UAT testers per the playbook in `docs/UAT_RESEARCHER_PLAN.md`.

### §4. Rollback procedure

If a new commit breaks production (broken page, traceback in the log, data corruption), roll back the source — Streamlit Cloud auto-redeploys on every push to the watched branch.

**4.1 Identify the last good commit**

```bash
git log --oneline -n 20
```

Pick the last SHA that you know was working (e.g. `a1b2c3d`).

**4.2 Revert (safest)**

```bash
git checkout main
git pull origin main
git revert <bad-sha>          # repeat for each bad commit, newest first
git push origin main
```

Streamlit Cloud picks up the push within ~30 seconds and rebuilds.

**4.3 Hard reset (only if revert produces conflicts)**

> Rewrites history and forces a push; coordinate with collaborators first.

```bash
git checkout main
git reset --hard <last-good-sha>
git push --force-with-lease origin main
```

**4.4 Database rollback**

If the bad commit also wrote bad data into Postgres:

1. In the Neon dashboard, open **Branches**.
2. Click **Restore** next to the timestamped backup taken before the bad deploy. Neon keeps a 7-day point-in-time history on the free tier.
3. Confirm. The branch swap takes ~10 seconds; reload the live URL.

**4.5 Verify the rollback**

Repeat the verification checklist in §3.

### §5. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Red banner: *"Konfigurasi belum lengkap"* | `CDT_DATABASE_URL` missing or misspelled. | Re-enter the secret (§2.3); reboot the app. |
| `psycopg2.OperationalError: SSL connection closed` | Idle Neon connection killed; pre-ping retries. | Refresh the page once. Persistent? Check Neon status. |
| Build log: `ERROR: Could not find a version that satisfies the requirement` | A pinned version was yanked. | Bump the version in `requirements.txt`, push. |
| App boots but writes "disappear" after redeploy | App is using SQLite, not Postgres. | The startup guard should have caught this. If on Cloud, check secrets. If local, verify `echo $CDT_DATABASE_URL`. |
| `streamlit run app.py` works locally but Cloud fails | Python version skew. | Check that `.python-version` matches Cloud's pinned version (3.11). |
| Researcher view says *"Mode peneliti tidak aktif"* | `CDT_RESEARCHER_PASSWORD` is unset. | Add it to Streamlit Cloud Secrets and reboot. |

### File reference (deployment-relevant)

| File | Purpose |
|---|---|
| `requirements.txt` | Exact-pinned dependencies for reproducible builds. |
| `.python-version` | Pins Streamlit Cloud to Python 3.11. |
| `.streamlit/config.toml` | Theme, headless server, disabled telemetry. |
| `.streamlit/secrets.toml.example` | Documents the secret keys; copy to `secrets.toml` locally. |
| `app.py` (startup guard) | Refuses to start on Cloud without `CDT_DATABASE_URL`. |
| `docs/DEPLOYMENT_PHASE1.md` | Background on the SQLite → Postgres migration. |

---

## Coding Conventions

- **Language:** all UI text, feedback templates, and user-facing strings in **Bahasa Indonesia** (EYD V).
- **Datetime:** always `datetime.now(timezone.utc)` — never the deprecated `datetime.utcnow()`.
- **DB session:** use `with get_session() as sess:` — never hold a session across Streamlit reruns.
- **Tests:** in-memory SQLite via `tests/conftest.py` fixtures; never import Streamlit in tests.
- **Logging:** `logger = logging.getLogger(__name__)` at module level; never `print()` in app code.

### Do NOT

- Change the tech stack (Streamlit, SQLAlchemy, pandas, Plotly, pytest).
- Add new biases beyond DEI, OCS, LAI.
- Add LLM/RAG to feedback (documented as future work).
- Restructure the folder layout or rename modules.
- Use `datetime.utcnow()` (deprecated).
- Use `print()` in production code (use logging).
- Commit `*.db` files (they are gitignored).

---

## Technology Stack

| Layer | Technology |
|---|---|
| UI | Streamlit |
| Backend | Python 3.11+ |
| Database | SQLite (dev) / PostgreSQL (prod via `CDT_DATABASE_URL`) |
| ORM | SQLAlchemy 2.0+ |
| Charts | Plotly |
| Auth | bcrypt + per-user rate limiting |
| Testing | pytest |
| Hosting | Streamlit Community Cloud + Neon Postgres |

---

## Research Context

This system is developed as part of a final thesis at **Institut Teknologi Bandung (ITB)**, School of Electrical Engineering and Informatics (STEI), Information Systems and Technology program.

**Author:** Arvyno Pranata Limahardja (NIM: 18222007)
**Supervisor:** Prof. Dr. Ir. Suhono Harso Supangkat, M.Eng.

---

## License

This project is part of an academic thesis. All rights reserved.
