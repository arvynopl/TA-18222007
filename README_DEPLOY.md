# Deployment Guide — Streamlit Community Cloud

This guide walks through deploying the CDT Bias Detection prototype from
GitHub to Streamlit Community Cloud, end to end. It is written so a
non-developer (e.g. a thesis advisor) can follow it as a checklist. Every
step lists what to click and what success looks like.

> **Reading order:** Section 1 (Neon) → Section 2 (Streamlit Cloud) →
> Section 3 (verification) → Section 4 (rollback if needed).

---

## Prerequisites

- A GitHub account with access to the repository `arvynopl/TA-18222007`.
- A web browser (Chrome / Edge / Firefox / Safari).
- 15–30 minutes of uninterrupted time for the first deploy.

You do **not** need a local Python install for production deployment.
Everything happens in the browser.

---

## 1. One-time Neon Postgres setup

The app needs a managed Postgres database because Streamlit Cloud's
container filesystem is wiped on every redeploy. Neon's free tier is
sufficient for UAT (≥100 testers).

### 1.1 Create the Neon project

1. Go to <https://neon.tech> and sign in with GitHub.
2. Click **New Project**.
3. Fill in:
   - **Project name:** `cdt-bias-uat` (any name is fine).
   - **Postgres version:** keep the default (16+).
   - **Region:** pick the option closest to Indonesia. As of 2026 the
     nearest is `Asia Pacific (Singapore) — ap-southeast-1`. If that is
     unavailable, pick `Asia Pacific (Tokyo)` or `US West`.
   - **Database name:** `cdt_bias` (any name is fine, just remember it).
4. Click **Create project**.

**Success check:** you land on the project dashboard and see a green
"Active" badge next to the project name.

### 1.2 Copy the connection string

1. On the project dashboard, click **Connection Details** (or the
   **Dashboard → Connection string** tab).
2. Make sure the **Pooled connection** toggle is **ON** (Streamlit Cloud's
   serverless containers benefit from the Neon pooler).
3. Click the **copy** icon next to the URL. The string looks like:

   ```
   postgresql://neondb_owner:abc123XYZ@ep-cool-name-12345.ap-southeast-1.aws.neon.tech/cdt_bias?sslmode=require
   ```

4. Paste it into a temporary scratchpad — you will use it in step 2.3.

> **Security note:** treat this string like a password. Do not paste it
> into chat, email, or commit it to git. The repo's `.gitignore` already
> blocks the file `.streamlit/secrets.toml`.

### 1.3 (Optional) seed the database from your local machine

This is **optional** because the app calls `run_seed()` on its first
boot and the operation is idempotent. If you prefer to pre-seed:

```bash
git clone https://github.com/arvynopl/TA-18222007.git
cd TA-18222007
pip install -r requirements.txt
export CDT_DATABASE_URL='<paste-neon-url-here>'
python -m database.seed
```

**Success check:** the script prints `Seed complete` and exits with code 0.

---

## 2. Streamlit Community Cloud setup

### 2.1 Sign in

1. Go to <https://streamlit.io/cloud>.
2. Click **Sign in** and authorise with the GitHub account that owns
   (or has access to) `arvynopl/TA-18222007`.

### 2.2 Create the app

1. Click **Create app** → **Deploy a public app from GitHub**.
2. Fill in:
   - **Repository:** `arvynopl/TA-18222007`
   - **Branch:** `main` (or whatever branch you intend to deploy)
   - **Main file path:** `app.py`
   - **App URL:** pick a subdomain, e.g. `cdt-bias-uat`. The full URL
     will be `https://cdt-bias-uat.streamlit.app`.
3. **Do not click Deploy yet.** Open **Advanced settings** first.

### 2.3 Add the secret

In **Advanced settings → Secrets**, paste:

```toml
CDT_DATABASE_URL = "postgresql://<user>:<pass>@<host>.neon.tech/<db>?sslmode=require"
```

Replace the placeholder with the real Neon URL from step 1.2. Keep the
double quotes. Then click **Save**.

> **Why this matters:** the app contains a startup guard
> (`app.py:_looks_like_streamlit_cloud`). If it detects Streamlit Cloud
> *and* `CDT_DATABASE_URL` is unset, it refuses to boot — preventing the
> silent SQLite-data-loss footgun.

### 2.4 Confirm Python version

Streamlit Cloud reads `.python-version` from the repo root and pins to
the version listed there (currently `3.11`). No action needed; just
confirm the **Python version** dropdown in **Advanced settings** shows
`3.11` (or "Auto").

### 2.5 Deploy

Click **Deploy**. The first build takes 3–5 minutes (installing the
pinned dependencies in `requirements.txt`). Watch the live log for
errors. You will see:

```
[manager] Installing requirements: streamlit==1.39.0, sqlalchemy==2.0.36, ...
[manager] Your app is in the oven
...
[manager] Your app is live!
```

---

## 3. First-deploy verification checklist

Open the live URL (e.g. `https://cdt-bias-uat.streamlit.app`) and walk
through this list. Tick each box mentally before declaring success.

- [ ] **Page loads.** The hero shows *"Kenali Pola Investasi Anda"* and
      the *Beranda* navigation tab is highlighted. No red error banner
      at the top.
- [ ] **No startup guard fired.** If you instead see a red box that
      says *"Konfigurasi belum lengkap"*, your secret is missing or
      misnamed. Go back to step 2.3.
- [ ] **DB init succeeded.** The first page render runs `run_seed()`.
      In the Streamlit Cloud log you should see no `OperationalError`
      or `psycopg2` traceback. The Neon dashboard shows the database
      size jump from ~0 to ~5 MB once seeded.
- [ ] **Smoke test — register.** Click **Daftar Akun Baru** with a
      throwaway username (e.g. `smoketest1`) and password. Confirm you
      land on the survey page.
- [ ] **Smoke test — simulation.** Skip the survey or fill it in, then
      open *Simulasi Investasi*. Confirm round 1 of 14 renders with a
      candlestick chart and 12 stocks listed.
- [ ] **Smoke test — persistence.** Refresh the page. Your simulation
      progress should still be there — proving Postgres (not SQLite) is
      backing the writes.
- [ ] **Neon row count.** In the Neon SQL editor run:

      ```sql
      SELECT COUNT(*) FROM users;
      SELECT COUNT(*) FROM market_snapshots;
      ```

      `users` should be ≥ 1 (your smoketest account). `market_snapshots`
      should be ~2826.
- [ ] **No data in repo.** Run `git status` locally — you should see
      no new files. The app must never write to the container disk.

If every box is ticked, the deploy is good. Share the URL with UAT
testers.

---

## 4. Rollback procedure

If a new commit breaks production (broken page, traceback in the log,
data corruption), roll back the source — Streamlit Cloud
auto-redeploys on every push to the watched branch.

### 4.1 Identify the last good commit

```bash
git log --oneline -n 20
```

Pick the last SHA that you know was working (e.g. `a1b2c3d`).

### 4.2 Revert

The safest option is **revert** (creates a new commit that undoes the
bad changes; nothing rewrites history):

```bash
git checkout main
git pull origin main
git revert <bad-sha>          # repeat for each bad commit, newest first
git push origin main
```

Streamlit Cloud picks up the push within ~30 seconds and rebuilds.

### 4.3 (If revert is not enough) hard reset

Use this **only** if the bad commit corrupted the working tree and a
revert produces conflicts. **This rewrites history and forces a push;
coordinate with collaborators first.**

```bash
git checkout main
git reset --hard <last-good-sha>
git push --force-with-lease origin main
```

### 4.4 Database rollback

If the bad commit also wrote bad data into Postgres:

1. In the Neon dashboard, open **Branches**.
2. Click **Restore** next to the timestamped backup taken before the
   bad deploy. Neon keeps a 7-day point-in-time history on the free
   tier.
3. Confirm. The branch swap takes ~10 seconds; reload the live URL.

### 4.5 Verify the rollback

Repeat the [verification checklist](#3-first-deploy-verification-checklist).

---

## Troubleshooting

| Symptom                                              | Likely cause                                  | Fix                                              |
| ---------------------------------------------------- | --------------------------------------------- | ------------------------------------------------ |
| Red banner: *"Konfigurasi belum lengkap"*            | `CDT_DATABASE_URL` missing or misspelled.     | Re-enter the secret (step 2.3); reboot the app. |
| `psycopg2.OperationalError: SSL connection closed`   | Idle Neon connection killed; pre-ping retries. | Refresh the page once. Persistent? Check Neon status. |
| Build log: `ERROR: Could not find a version that satisfies the requirement` | A pinned version was yanked.                  | Bump the version in `requirements.txt`, push.   |
| App boots but writes "disappear" after redeploy      | App is using SQLite, not Postgres.            | The startup guard should have caught this. If on Cloud, check secrets. If local, verify `echo $CDT_DATABASE_URL`. |
| `streamlit run app.py` works locally but Cloud fails | Python version skew.                          | Check that `.python-version` matches Cloud's pinned version (3.11). |

---

## File reference

| File                              | Purpose                                                     |
| --------------------------------- | ----------------------------------------------------------- |
| `requirements.txt`                | Exact-pinned dependencies for reproducible builds.          |
| `.python-version`                 | Pins Streamlit Cloud to Python 3.11.                        |
| `.streamlit/config.toml`          | Theme, headless server, disabled telemetry.                 |
| `.streamlit/secrets.toml.example` | Documents the secret keys; copy to `secrets.toml` locally.  |
| `app.py` (startup guard)          | Refuses to start on Cloud without `CDT_DATABASE_URL`.       |
| `docs/DEPLOYMENT_PHASE1.md`       | Background on the SQLite → Postgres migration.              |
